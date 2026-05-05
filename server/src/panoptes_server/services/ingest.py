"""Apply IngestEvent payloads to the database, idempotently.

Workflow rows are keyed by `run_id`; jobs by `(workflow_id, internal_id)`;
JobEvent rows by `(job_id, timestamp, event)`. Re-POSTing the same batch
must not produce duplicate rows.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone


def _to_utc(dt: datetime) -> datetime:
    """Coerce any datetime to a tz-aware UTC datetime.

    Plugin-emitted timestamps are already UTC-aware; bare ISO strings
    (no offset) are interpreted as UTC by convention.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from panoptes_server.models import (
    Job, JobEvent, JobStatus, Workflow, WorkflowDag, WorkflowStatus,
)
from panoptes_server.schemas import IngestEvent
from panoptes_server.services import pubsub


async def _get_or_create_workflow(
    session: AsyncSession, run_id: str, started_at: datetime
) -> Workflow:
    result = await session.exec(select(Workflow).where(Workflow.run_id == run_id))
    wf = result.first()
    if wf is None:
        wf = Workflow(run_id=run_id, started_at=started_at, status=WorkflowStatus.RUNNING)
        session.add(wf)
        await session.flush()
    return wf


async def _get_or_create_job(
    session: AsyncSession, workflow_id: int, internal_id: int, rule: str
) -> Job:
    result = await session.exec(
        select(Job).where(
            Job.workflow_id == workflow_id, Job.internal_id == internal_id
        )
    )
    job = result.first()
    if job is None:
        job = Job(workflow_id=workflow_id, internal_id=internal_id, rule=rule)
        session.add(job)
        await session.flush()
    return job


async def _record_event(
    session: AsyncSession,
    job_id: int,
    timestamp: datetime,
    event: str,
    detail: dict | None = None,
) -> None:
    """Insert a JobEvent; swallow unique-constraint conflicts (idempotent replays)."""
    payload = json.dumps(detail) if detail else None
    je = JobEvent(job_id=job_id, timestamp=timestamp, event=event, detail=payload)
    session.add(je)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()


async def apply_event(
    session: AsyncSession, run_id: str, ev: IngestEvent
) -> None:
    name = ev.event.upper()
    ts = _to_utc(ev.ts)

    if name == "WORKFLOW_STARTED":
        wf = await _get_or_create_workflow(session, run_id, ts)
        if ev.snakemake_version is not None:
            wf.snakemake_version = ev.snakemake_version
        if ev.snakefile is not None:
            wf.snakefile = ev.snakefile
        if ev.cwd is not None:
            wf.cwd = ev.cwd
        if ev.total_jobs is not None:
            wf.total_jobs = ev.total_jobs
        if ev.workflow_name is not None and wf.name is None:
            wf.name = ev.workflow_name
        wf.status = WorkflowStatus.RUNNING
        session.add(wf)
        await session.flush()
        return

    if name in {"WORKFLOW_DONE", "WORKFLOW_FINISHED"}:
        wf = await _get_or_create_workflow(session, run_id, ts)
        wf.status = WorkflowStatus.DONE
        wf.completed_at = ts
        session.add(wf)
        await session.flush()
        return

    if name == "RUN_INFO":
        # informational; no DB changes beyond ensuring the workflow exists
        await _get_or_create_workflow(session, run_id, ts)
        return

    if name == "RULEGRAPH":
        wf = await _get_or_create_workflow(session, run_id, ts)
        if ev.nodes is not None and ev.edges is not None:
            payload = json.dumps({"nodes": ev.nodes, "edges": ev.edges})
            existing = await session.get(WorkflowDag, wf.id)
            if existing is None:
                session.add(WorkflowDag(
                    workflow_id=wf.id, payload=payload, captured_at=ts,
                ))
            else:
                existing.payload = payload
                existing.captured_at = ts
                session.add(existing)
            await session.flush()
        return

    if name == "PROGRESS":
        wf = await _get_or_create_workflow(session, run_id, ts)
        if ev.total is not None and wf.total_jobs is None:
            wf.total_jobs = ev.total
        session.add(wf)
        await session.flush()
        return

    # Job-level events — must have internal_id.
    if ev.internal_id is None:
        return  # ignore unhandled or malformed events

    wf = await _get_or_create_workflow(session, run_id, ts)
    rule = ev.rule or "<unknown>"
    job = await _get_or_create_job(session, wf.id, ev.internal_id, rule)
    if ev.rule and job.rule != ev.rule:
        job.rule = ev.rule
    if ev.wildcards is not None and job.wildcards is None:
        job.wildcards = json.dumps(ev.wildcards)
    if ev.threads is not None and job.threads is None:
        job.threads = ev.threads
    if ev.log is not None and job.log_path is None:
        job.log_path = ev.log

    if name == "JOB_STARTED":
        job.status = JobStatus.RUNNING
        if job.started_at is None:
            job.started_at = ts
    elif name == "JOB_INFO":
        # arrives at scheduling time; treat as pending unless already running
        if job.status == JobStatus.PENDING:
            pass
    elif name == "JOB_FINISHED":
        job.status = JobStatus.DONE
        job.finished_at = ts
    elif name == "JOB_ERROR":
        job.status = JobStatus.ERROR
        job.finished_at = ts
        wf.status = WorkflowStatus.ERROR
        session.add(wf)

    session.add(job)
    await session.flush()
    await _record_event(session, job.id, ts, name, ev.detail)


async def apply_batch(
    session: AsyncSession, run_id: str, events: list[IngestEvent]
) -> int:
    for ev in events:
        await apply_event(session, run_id, ev)
    await _maybe_mark_complete(session, run_id, events)
    await session.commit()

    # Publish a delta so WebSocket subscribers can invalidate caches
    # immediately instead of waiting for their next 2s poll. We
    # resolve the workflow_id post-commit; if the run is brand new
    # this is the first time it has an integer id.
    if events:
        wf = (
            await session.exec(select(Workflow).where(Workflow.run_id == run_id))
        ).first()
        if wf is not None:
            names = sorted({ev.event.upper() for ev in events})
            await pubsub.publish(
                wf.id,
                {"type": "events", "names": names, "run_id": run_id},
            )
    return len(events)


async def _maybe_mark_complete(
    session: AsyncSession, run_id: str, events: list[IngestEvent]
) -> None:
    """Belt-and-braces: if every known job is finished and no JOB_*/PROGRESS
    arrived in this batch (i.e. the snakemake run has gone quiet), mark
    the workflow done. Covers the case where the plugin is killed before
    its synthetic WORKFLOW_DONE is flushed.
    """
    has_job_traffic = any(
        ev.event.upper() in {"JOB_STARTED", "JOB_INFO", "JOB_FINISHED",
                              "JOB_ERROR", "PROGRESS"}
        for ev in events
    )
    if has_job_traffic:
        return
    result = await session.exec(select(Workflow).where(Workflow.run_id == run_id))
    wf = result.first()
    if wf is None or wf.status != WorkflowStatus.RUNNING:
        return
    jobs = (
        await session.exec(select(Job).where(Job.workflow_id == wf.id))
    ).all()
    if not jobs:
        return
    if all(j.status == JobStatus.DONE for j in jobs):
        wf.status = WorkflowStatus.DONE
        if wf.completed_at is None:
            latest = max(
                (j.finished_at for j in jobs if j.finished_at), default=None
            )
            wf.completed_at = _to_utc(latest) if latest is not None else None
        session.add(wf)
        await session.flush()
