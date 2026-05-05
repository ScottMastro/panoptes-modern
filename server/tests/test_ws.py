"""WebSocket pub/sub: ingest publishes a delta to subscribers."""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from panoptes_server import db
from panoptes_server.main import create_app
from panoptes_server.services import pubsub


@pytest.mark.asyncio
async def test_pubsub_bus_delivers_messages():
    """Two subscribers on the same workflow id both receive the message;
    a different workflow id sees nothing."""
    q1 = await pubsub.subscribe(1)
    q2 = await pubsub.subscribe(1)
    q3 = await pubsub.subscribe(2)
    try:
        delivered = await pubsub.publish(1, {"type": "events", "names": ["X"]})
        assert delivered == 2

        msg1 = await asyncio.wait_for(q1.get(), timeout=1)
        msg2 = await asyncio.wait_for(q2.get(), timeout=1)
        assert msg1 == msg2 == {"type": "events", "names": ["X"]}
        assert q3.empty()
    finally:
        await pubsub.unsubscribe(1, q1)
        await pubsub.unsubscribe(1, q2)
        await pubsub.unsubscribe(2, q3)


@pytest.mark.asyncio
async def test_pubsub_full_queue_drops_oldest():
    q = await pubsub.subscribe(99)
    try:
        for i in range(70):
            await pubsub.publish(99, {"type": "events", "names": [str(i)]})
        last = q.get_nowait()
        assert last["type"] == "events"
    finally:
        await pubsub.unsubscribe(99, q)


@pytest.fixture
def ws_client():
    """Sync TestClient with a fresh in-memory DB. TestClient's `with`
    block triggers the FastAPI lifespan, which initializes the engine
    on the same event loop the WS handler runs on."""
    os.environ["PANOPTES_DB_URL"] = "sqlite+aiosqlite:///:memory:"
    db._engine = None
    db._sessionmaker = None
    app = create_app()
    with TestClient(app) as client:
        yield client
    # Without disposing the engine, lingering aiosqlite tasks block
    # process exit forever. Dispose on the same loop TestClient used.
    if db._engine is not None:
        engine = db._engine
        try:
            asyncio.get_event_loop().run_until_complete(engine.dispose())
        except RuntimeError:
            asyncio.new_event_loop().run_until_complete(engine.dispose())
        db._engine = None
        db._sessionmaker = None


def test_websocket_receives_publish_after_ingest(ws_client):
    """End-to-end: subscribe to /ws/{wf_id}, POST to /ingest, assert
    the delta arrives on the WebSocket."""
    ws_client.post(
        "/api/v1/ingest",
        json={
            "run_id": "ws-1",
            "events": [
                {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00"}
            ],
        },
    )
    wf = ws_client.get("/api/v1/workflows").json()[0]
    wf_id = wf["id"]

    with ws_client.websocket_connect(f"/api/v1/ws/{wf_id}") as ws:
        hello = ws.receive_json()
        assert hello == {"type": "hello", "workflow_id": wf_id}

        ws_client.post(
            "/api/v1/ingest",
            json={
                "run_id": "ws-1",
                "events": [
                    {"event": "JOB_STARTED",
                     "ts": "2026-01-01T00:00:01",
                     "internal_id": 1, "rule": "x"},
                ],
            },
        )
        msg = ws.receive_json()
        assert msg["type"] == "events"
        assert "JOB_STARTED" in msg["names"]


def test_websocket_404_on_unknown_workflow(ws_client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with ws_client.websocket_connect("/api/v1/ws/9999"):
            pass
    assert exc_info.value.code == 4404
