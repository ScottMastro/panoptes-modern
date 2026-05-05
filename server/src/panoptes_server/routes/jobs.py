from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from panoptes_server.db import get_session
from panoptes_server.models import Job, JobEvent, Workflow
from panoptes_server.schemas import JobLogRead, JobRead, serialize_utc
from panoptes_server.services.log_tail import LogAccessError, tail_log

router = APIRouter()


@router.get("/{workflow_id}/jobs", response_model=list[JobRead])
async def list_jobs(
    workflow_id: int, session: AsyncSession = Depends(get_session)
) -> list[Job]:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    result = await session.exec(
        select(Job).where(Job.workflow_id == workflow_id).order_by(Job.internal_id)
    )
    return result.all()


@router.get("/{workflow_id}/jobs/{job_id}", response_model=JobRead)
async def get_job(
    workflow_id: int,
    job_id: int,
    session: AsyncSession = Depends(get_session),
) -> Job:
    job = await session.get(Job, job_id)
    if job is None or job.workflow_id != workflow_id:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found in workflow {workflow_id}",
        )
    return job


@router.get("/{workflow_id}/jobs/{job_id}/log", response_model=JobLogRead)
async def get_job_log(
    workflow_id: int,
    job_id: int,
    lines: int = 200,
    session: AsyncSession = Depends(get_session),
) -> JobLogRead:
    job = await session.get(Job, job_id)
    if job is None or job.workflow_id != workflow_id:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found in workflow {workflow_id}",
        )
    if not job.log_path:
        raise HTTPException(status_code=404, detail="Job has no log path")
    wf = await session.get(Workflow, workflow_id)
    lines = max(1, min(lines, 5000))
    try:
        result = tail_log(job.log_path, wf.cwd if wf else None, max_lines=lines)
    except LogAccessError as e:
        # Path-escape and missing-file collapse into 404 — both mean
        # "no readable log here". Don't leak which.
        raise HTTPException(status_code=404, detail=str(e)) from e
    return JobLogRead(**result)


@router.get("/{workflow_id}/jobs/{job_id}/events")
async def get_job_events(
    workflow_id: int,
    job_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    job = await session.get(Job, job_id)
    if job is None or job.workflow_id != workflow_id:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found in workflow {workflow_id}",
        )
    rows = (
        await session.exec(
            select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.timestamp)
        )
    ).all()
    return [
        {
            "id": e.id,
            "timestamp": serialize_utc(e.timestamp),
            "event": e.event,
            "detail": e.detail,
        }
        for e in rows
    ]
