"""WebSocket endpoint for live workflow updates.

Subscribes to the per-workflow pub/sub bus; forwards published deltas
to the client. The protocol is intentionally tiny — every message is
a JSON object with a `type` field. The client treats every message as
an "invalidate this workflow's queries" signal; the contents of the
message are diagnostic only.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from panoptes_server import db
from panoptes_server.models import Workflow
from panoptes_server.services import pubsub

log = logging.getLogger(__name__)

router = APIRouter()

# How often to send a keepalive ping so reverse proxies don't kill
# idle connections; clients also use this as a "still connected"
# heartbeat.
_KEEPALIVE_SECS = 25.0


async def _workflow_exists(workflow_id: int) -> bool:
    sm = db._sessionmaker
    assert sm is not None, "db not initialized"
    async with sm() as session:  # type: AsyncSession
        result = await session.exec(
            select(Workflow.id).where(Workflow.id == workflow_id)
        )
        return result.first() is not None


@router.websocket("/ws/{workflow_id}")
async def workflow_events(websocket: WebSocket, workflow_id: int) -> None:
    if not await _workflow_exists(workflow_id):
        # 4404: app-level "not found"; close before accept so we don't
        # leak a half-open socket.
        await websocket.close(code=4404, reason="workflow not found")
        return

    await websocket.accept()
    queue = await pubsub.subscribe(workflow_id)
    await websocket.send_json({"type": "hello", "workflow_id": workflow_id})

    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=_KEEPALIVE_SECS)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("ws: unexpected error for wf=%d", workflow_id)
    finally:
        await pubsub.unsubscribe(workflow_id, queue)
