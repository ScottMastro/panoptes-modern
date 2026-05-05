"""Smoke tests for the 8 mirrored REST endpoints + service-info.

Mirrors the intent of the legacy panoptes/tests/api_test.py (status codes,
shape of responses, 404 on missing IDs, rename, delete) against the
new /api/v1 surface.
"""
import pytest

pytestmark = pytest.mark.asyncio


async def _seed_workflow(client, run_id="r1", name=None):
    payload = {
        "run_id": run_id,
        "events": [
            {
                "event": "WORKFLOW_STARTED",
                "ts": "2026-01-01T00:00:00",
                "snakemake_version": "8.20.0",
                "snakefile": "/tmp/Snakefile",
                "cwd": "/tmp",
                "total_jobs": 3,
                "workflow_name": name,
            }
        ],
    }
    r = await client.post("/api/v1/ingest", json=payload)
    assert r.status_code == 200
    workflows = (await client.get("/api/v1/workflows")).json()
    return next(w for w in workflows if w["run_id"] == run_id)


async def test_service_info(client):
    r = await client.get("/api/v1/service-info")
    assert r.status_code == 200
    assert r.json()["status"] == "running"


async def test_list_workflows_empty(client):
    r = await client.get("/api/v1/workflows")
    assert r.status_code == 200
    assert r.json() == []


async def test_get_workflow_404(client):
    r = await client.get("/api/v1/workflows/999")
    assert r.status_code == 404


async def test_get_jobs_404_on_unknown_workflow(client):
    r = await client.get("/api/v1/workflows/999/jobs")
    assert r.status_code == 404


async def test_workflow_lifecycle(client):
    wf = await _seed_workflow(client, run_id="lifecycle")
    wf_id = wf["id"]

    r = await client.get(f"/api/v1/workflows/{wf_id}")
    assert r.status_code == 200
    assert r.json()["snakemake_version"] == "8.20.0"
    assert r.json()["total_jobs"] == 3

    r = await client.put(
        f"/api/v1/workflows/{wf_id}", json={"name": "renamed-run"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "renamed-run"

    r = await client.put(f"/api/v1/workflows/{wf_id}", json={"name": "  "})
    assert r.status_code == 400

    r = await client.delete(f"/api/v1/workflows/{wf_id}")
    assert r.status_code == 204

    r = await client.get(f"/api/v1/workflows/{wf_id}")
    assert r.status_code == 404


async def test_delete_all(client):
    await _seed_workflow(client, run_id="a")
    await _seed_workflow(client, run_id="b")
    r = await client.delete("/api/v1/workflows")
    assert r.status_code == 200
    r = await client.get("/api/v1/workflows")
    assert r.json() == []
