from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from panoptes_server.db import get_session
from panoptes_server.schemas import IngestBatch, IngestResponse
from panoptes_server.services.ingest import apply_batch

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    batch: IngestBatch, session: AsyncSession = Depends(get_session)
) -> IngestResponse:
    accepted = await apply_batch(session, batch.run_id, batch.events)
    return IngestResponse(accepted=accepted)
