"""Ingest endpoint: LogEvent payload → DB state, plus idempotency."""
import pytest

pytestmark = pytest.mark.asyncio


def _batch(run_id, *events):
    return {"run_id": run_id, "events": list(events)}


async def test_responses_emit_utc_marked_iso(client):
    """API contract: every datetime field is ISO-8601 with an explicit
    UTC offset (`+00:00`). Without this the JS UI would parse them as
    local time and offsets would creep in.
    """
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "tz-run",
            {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T12:00:00",
             "snakemake_version": "9.13"},
            {"event": "JOB_STARTED", "ts": "2026-01-01T12:00:01",
             "internal_id": 1, "rule": "x"},
            {"event": "JOB_FINISHED", "ts": "2026-01-01T12:00:02",
             "internal_id": 1, "rule": "x"},
        ),
    )
    workflows = (await client.get("/api/v1/workflows")).json()
    wf = workflows[0]
    assert wf["started_at"].endswith("+00:00")

    wf_id = wf["id"]
    jobs = (await client.get(f"/api/v1/workflows/{wf_id}/jobs")).json()
    assert jobs[0]["started_at"].endswith("+00:00")
    assert jobs[0]["finished_at"].endswith("+00:00")

    events = (await client.get(
        f"/api/v1/workflows/{wf_id}/jobs/{jobs[0]['id']}/events"
    )).json()
    for e in events:
        assert e["timestamp"].endswith("+00:00")


async def test_full_run(client):
    payload = _batch(
        "run-1",
        {
            "event": "WORKFLOW_STARTED",
            "ts": "2026-01-01T00:00:00",
            "snakemake_version": "8.20.0",
            "snakefile": "/tmp/Snakefile",
            "total_jobs": 2,
        },
        {
            "event": "JOB_STARTED",
            "ts": "2026-01-01T00:00:01",
            "internal_id": 0,
            "rule": "all",
            "wildcards": {"sample": "A"},
            "threads": 4,
            "log": "/tmp/log/all.log",
        },
        {
            "event": "JOB_FINISHED",
            "ts": "2026-01-01T00:00:05",
            "internal_id": 0,
            "rule": "all",
        },
        {"event": "WORKFLOW_DONE", "ts": "2026-01-01T00:00:06"},
    )
    r = await client.post("/api/v1/ingest", json=payload)
    assert r.status_code == 200
    assert r.json()["accepted"] == 4

    workflows = (await client.get("/api/v1/workflows")).json()
    assert len(workflows) == 1
    wf = workflows[0]
    assert wf["status"] == "done"
    assert wf["snakemake_version"] == "8.20.0"
    assert wf["completed_at"] is not None

    jobs = (await client.get(f"/api/v1/workflows/{wf['id']}/jobs")).json()
    assert len(jobs) == 1
    job = jobs[0]
    assert job["status"] == "done"
    assert job["rule"] == "all"
    assert job["threads"] == 4
    assert job["log_path"] == "/tmp/log/all.log"


async def test_idempotent_replay(client):
    payload = _batch(
        "run-2",
        {
            "event": "WORKFLOW_STARTED",
            "ts": "2026-01-01T00:00:00",
            "total_jobs": 1,
        },
        {
            "event": "JOB_STARTED",
            "ts": "2026-01-01T00:00:01",
            "internal_id": 7,
            "rule": "step",
        },
        {
            "event": "JOB_FINISHED",
            "ts": "2026-01-01T00:00:02",
            "internal_id": 7,
            "rule": "step",
        },
    )
    for _ in range(3):
        r = await client.post("/api/v1/ingest", json=payload)
        assert r.status_code == 200

    workflows = (await client.get("/api/v1/workflows")).json()
    assert len(workflows) == 1
    jobs = (await client.get(f"/api/v1/workflows/{workflows[0]['id']}/jobs")).json()
    assert len(jobs) == 1


async def test_concurrent_runs_isolated(client):
    for run_id in ("alpha", "beta"):
        await client.post(
            "/api/v1/ingest",
            json=_batch(
                run_id,
                {
                    "event": "WORKFLOW_STARTED",
                    "ts": "2026-01-01T00:00:00",
                    "total_jobs": 1,
                },
                {
                    "event": "JOB_STARTED",
                    "ts": "2026-01-01T00:00:01",
                    "internal_id": 1,
                    "rule": "shared",
                },
            ),
        )

    workflows = (await client.get("/api/v1/workflows")).json()
    assert len(workflows) == 2
    run_ids = {w["run_id"] for w in workflows}
    assert run_ids == {"alpha", "beta"}
    for w in workflows:
        jobs = (await client.get(f"/api/v1/workflows/{w['id']}/jobs")).json()
        assert len(jobs) == 1
        assert jobs[0]["internal_id"] == 1


async def test_completion_fallback_marks_workflow_done(client):
    """When a batch arrives with no job-traffic events and all known
    jobs are done, the workflow auto-transitions to done. Covers the
    case where the plugin's synthetic WORKFLOW_DONE was lost.
    """
    # First batch — start and finish one job.
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "fb-1",
            {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00",
             "snakemake_version": "9.13"},
            {"event": "JOB_STARTED", "ts": "2026-01-01T00:00:01",
             "internal_id": 1, "rule": "step"},
            {"event": "JOB_FINISHED", "ts": "2026-01-01T00:00:02",
             "internal_id": 1, "rule": "step"},
        ),
    )
    workflows = (await client.get("/api/v1/workflows")).json()
    assert workflows[0]["status"] == "running"

    # Second batch with no job-traffic — the completion fallback fires.
    await client.post(
        "/api/v1/ingest",
        json={"run_id": "fb-1", "events": []},
    )
    workflows = (await client.get("/api/v1/workflows")).json()
    assert workflows[0]["status"] == "done"
    assert workflows[0]["completed_at"] is not None


async def test_stats_endpoint(client):
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "stats-run",
            {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00"},
            {"event": "JOB_STARTED", "ts": "2026-01-01T00:00:01",
             "internal_id": 1, "rule": "align"},
            {"event": "JOB_FINISHED", "ts": "2026-01-01T00:00:05",
             "internal_id": 1, "rule": "align"},
            {"event": "JOB_STARTED", "ts": "2026-01-01T00:00:06",
             "internal_id": 2, "rule": "align"},
            {"event": "JOB_STARTED", "ts": "2026-01-01T00:00:07",
             "internal_id": 3, "rule": "merge"},
        ),
    )
    wf_id = (await client.get("/api/v1/workflows")).json()[0]["id"]
    stats = (await client.get(f"/api/v1/workflows/{wf_id}/stats")).json()
    assert stats["total"] == 3
    assert stats["by_status"]["done"] == 1
    assert stats["by_status"]["running"] == 2
    rules = {r["rule"]: r for r in stats["by_rule"]}
    assert rules["align"]["total"] == 2
    assert rules["align"]["done"] == 1
    assert rules["align"]["mean_duration_seconds"] == 4.0
    assert rules["merge"]["mean_duration_seconds"] is None


async def test_job_events_endpoint(client):
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "ev-run",
            {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00"},
            {"event": "JOB_STARTED", "ts": "2026-01-01T00:00:01",
             "internal_id": 1, "rule": "x"},
            {"event": "JOB_FINISHED", "ts": "2026-01-01T00:00:02",
             "internal_id": 1, "rule": "x"},
        ),
    )
    wf_id = (await client.get("/api/v1/workflows")).json()[0]["id"]
    jobs = (await client.get(f"/api/v1/workflows/{wf_id}/jobs")).json()
    job_id = jobs[0]["id"]
    events = (await client.get(
        f"/api/v1/workflows/{wf_id}/jobs/{job_id}/events"
    )).json()
    assert [e["event"] for e in events] == ["JOB_STARTED", "JOB_FINISHED"]


async def test_rulegraph_capture_and_replay(client):
    """RULEGRAPH event creates a WorkflowDag row; replay updates in place."""
    nodes = [{"rule": "all"}, {"rule": "make_raw"}, {"rule": "transform"}]
    edges = [{"source": 1, "target": 2}, {"source": 2, "target": 0}]
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "dag-run",
            {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00"},
            {"event": "RULEGRAPH", "ts": "2026-01-01T00:00:01",
             "nodes": nodes, "edges": edges},
        ),
    )
    wf_id = (await client.get("/api/v1/workflows")).json()[0]["id"]
    dag = (await client.get(f"/api/v1/workflows/{wf_id}/dag")).json()
    assert [n["rule"] for n in dag["nodes"]] == ["all", "make_raw", "transform"]
    assert dag["edges"] == edges

    # Replay must not duplicate; it should still be a single row.
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "dag-run",
            {"event": "RULEGRAPH", "ts": "2026-01-01T00:00:02",
             "nodes": nodes, "edges": edges},
        ),
    )
    dag2 = (await client.get(f"/api/v1/workflows/{wf_id}/dag")).json()
    assert dag2["edges"] == edges


async def test_dag_404_when_absent(client):
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "no-dag-run",
            {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00"},
        ),
    )
    wf_id = (await client.get("/api/v1/workflows")).json()[0]["id"]
    r = await client.get(f"/api/v1/workflows/{wf_id}/dag")
    assert r.status_code == 404


async def test_job_error_marks_workflow(client):
    await client.post(
        "/api/v1/ingest",
        json=_batch(
            "run-err",
            {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00"},
            {
                "event": "JOB_STARTED",
                "ts": "2026-01-01T00:00:01",
                "internal_id": 1,
                "rule": "fail",
            },
            {
                "event": "JOB_ERROR",
                "ts": "2026-01-01T00:00:02",
                "internal_id": 1,
                "rule": "fail",
            },
        ),
    )
    workflows = (await client.get("/api/v1/workflows")).json()
    assert workflows[0]["status"] == "error"
    jobs = (await client.get(f"/api/v1/workflows/{workflows[0]['id']}/jobs")).json()
    assert jobs[0]["status"] == "error"
