"""Tests for the job log tail endpoint."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


async def _seed_job_with_log(client, log_path: str, cwd: str):
    await client.post(
        "/api/v1/ingest",
        json={
            "run_id": "log-run",
            "events": [
                {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00",
                 "cwd": cwd},
                {"event": "JOB_STARTED", "ts": "2026-01-01T00:00:01",
                 "internal_id": 1, "rule": "x", "log": log_path},
                {"event": "JOB_FINISHED", "ts": "2026-01-01T00:00:02",
                 "internal_id": 1, "rule": "x"},
            ],
        },
    )
    workflows = (await client.get("/api/v1/workflows")).json()
    wf_id = workflows[0]["id"]
    jobs = (await client.get(f"/api/v1/workflows/{wf_id}/jobs")).json()
    return wf_id, jobs[0]["id"]


async def test_tail_returns_last_n_lines(client, tmp_path):
    log = tmp_path / "out.log"
    log.write_text("\n".join(f"line-{i}" for i in range(50)))
    wf_id, job_id = await _seed_job_with_log(client, str(log), str(tmp_path))

    r = await client.get(
        f"/api/v1/workflows/{wf_id}/jobs/{job_id}/log?lines=5"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] == [f"line-{i}" for i in range(45, 50)]
    assert body["truncated"] is True
    assert body["size_bytes"] == log.stat().st_size


async def test_tail_404_when_file_missing(client, tmp_path):
    log = tmp_path / "gone.log"
    log.write_text("hello")
    wf_id, job_id = await _seed_job_with_log(client, str(log), str(tmp_path))
    log.unlink()
    r = await client.get(f"/api/v1/workflows/{wf_id}/jobs/{job_id}/log")
    assert r.status_code == 404


async def test_tail_rejects_path_outside_cwd(client, tmp_path):
    """Path-traversal sandbox: log_path that escapes the workflow's
    cwd is refused even when the file exists."""
    cwd = tmp_path / "run"
    cwd.mkdir()
    outside = tmp_path / "escapee.log"
    outside.write_text("secret")
    wf_id, job_id = await _seed_job_with_log(client, str(outside), str(cwd))
    r = await client.get(f"/api/v1/workflows/{wf_id}/jobs/{job_id}/log")
    assert r.status_code == 404


async def test_tail_resolves_relative_to_cwd(client, tmp_path):
    """Snakemake stores `log:` directive value verbatim — usually
    relative to the workflow's cwd. The endpoint must resolve it
    against cwd, not the server process's cwd.
    """
    cwd = tmp_path / "run"
    cwd.mkdir()
    log = cwd / "out" / "step.log"
    log.parent.mkdir(parents=True)
    log.write_text("hello world")
    # Pass the relative path the way snakemake would.
    wf_id, job_id = await _seed_job_with_log(client, "out/step.log", str(cwd))
    r = await client.get(f"/api/v1/workflows/{wf_id}/jobs/{job_id}/log")
    assert r.status_code == 200
    assert r.json()["lines"] == ["hello world"]


async def test_tail_404_when_no_log_path(client):
    """Job without a log_path returns 404 cleanly."""
    await client.post(
        "/api/v1/ingest",
        json={
            "run_id": "no-log-run",
            "events": [
                {"event": "WORKFLOW_STARTED", "ts": "2026-01-01T00:00:00"},
                {"event": "JOB_STARTED", "ts": "2026-01-01T00:00:01",
                 "internal_id": 1, "rule": "x"},
            ],
        },
    )
    workflows = (await client.get("/api/v1/workflows")).json()
    wf_id = workflows[0]["id"]
    jobs = (await client.get(f"/api/v1/workflows/{wf_id}/jobs")).json()
    job_id = jobs[0]["id"]
    r = await client.get(f"/api/v1/workflows/{wf_id}/jobs/{job_id}/log")
    assert r.status_code == 404
