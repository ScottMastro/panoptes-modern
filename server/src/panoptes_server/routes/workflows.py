from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import delete, select

import json

from panoptes_server.db import get_session
from panoptes_server.models import Job, JobEvent, Workflow, WorkflowDag
from panoptes_server.schemas import WorkflowDagRead, WorkflowRead, WorkflowRename
from panoptes_server.services.stats import workflow_stats

router = APIRouter()


@router.get("", response_model=list[WorkflowRead])
async def list_workflows(session: AsyncSession = Depends(get_session)) -> list[Workflow]:
    result = await session.exec(select(Workflow).order_by(Workflow.started_at.desc()))
    return result.all()


@router.get("/{workflow_id}", response_model=WorkflowRead)
async def get_workflow(
    workflow_id: int, session: AsyncSession = Depends(get_session)
) -> Workflow:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return wf


@router.put("/{workflow_id}", response_model=WorkflowRead)
async def rename_workflow(
    workflow_id: int,
    body: WorkflowRename,
    session: AsyncSession = Depends(get_session),
) -> Workflow:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must be non-empty")
    wf.name = name
    session.add(wf)
    await session.commit()
    await session.refresh(wf)
    return wf


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

    job_ids = (
        await session.exec(select(Job.id).where(Job.workflow_id == workflow_id))
    ).all()
    if job_ids:
        await session.exec(delete(JobEvent).where(JobEvent.job_id.in_(job_ids)))
    await session.exec(delete(Job).where(Job.workflow_id == workflow_id))
    await session.delete(wf)
    await session.commit()


@router.get("/{workflow_id}/dag", response_model=WorkflowDagRead)
async def get_workflow_dag(
    workflow_id: int, session: AsyncSession = Depends(get_session)
) -> WorkflowDagRead:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    dag = await session.get(WorkflowDag, workflow_id)
    if dag is None:
        raise HTTPException(
            status_code=404,
            detail="No DAG captured for this workflow",
        )
    payload = json.loads(dag.payload)
    return WorkflowDagRead(
        nodes=payload["nodes"],
        edges=payload["edges"],
        captured_at=dag.captured_at,
    )


@router.get("/{workflow_id}/stats")
async def get_workflow_stats(
    workflow_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    wf = await session.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return await workflow_stats(session, workflow_id)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_all_workflows(session: AsyncSession = Depends(get_session)) -> dict:
    await session.exec(delete(JobEvent))
    await session.exec(delete(Job))
    await session.exec(delete(Workflow))
    await session.commit()
    return {"msg": "all workflows deleted"}
