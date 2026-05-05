"""Aggregate stats for a workflow: counts per status, per-rule rollups."""
from __future__ import annotations

from collections import defaultdict

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from panoptes_server.models import Job, JobStatus


async def workflow_stats(session: AsyncSession, workflow_id: int) -> dict:
    rows = (
        await session.exec(select(Job).where(Job.workflow_id == workflow_id))
    ).all()

    status_counts = {s.value: 0 for s in JobStatus}
    per_rule: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "done": 0, "running": 0, "pending": 0, "error": 0,
                 "duration_sum": 0.0, "duration_count": 0}
    )

    for job in rows:
        status_counts[job.status.value] += 1
        bucket = per_rule[job.rule]
        bucket["total"] += 1
        bucket[job.status.value] += 1
        if job.started_at and job.finished_at:
            bucket["duration_sum"] += (
                job.finished_at - job.started_at
            ).total_seconds()
            bucket["duration_count"] += 1

    rules = []
    for rule, b in sorted(per_rule.items()):
        mean = (
            b["duration_sum"] / b["duration_count"]
            if b["duration_count"] else None
        )
        rules.append({
            "rule": rule,
            "total": b["total"],
            "done": b["done"],
            "running": b["running"],
            "pending": b["pending"],
            "error": b["error"],
            "mean_duration_seconds": mean,
        })

    return {
        "total": len(rows),
        "by_status": status_counts,
        "by_rule": rules,
    }
