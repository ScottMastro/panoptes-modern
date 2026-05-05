"""Buffering, flush, and retry behavior of the panoptes logger plugin."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import httpx
import pytest

from snakemake_logger_plugin_panoptes import LogHandler
from snakemake_logger_plugin_panoptes.settings import LoggerSettings


@dataclass
class _CommonSettings:
    printshellcmds: bool = False
    nocolor: bool = True
    quiet: object = None
    debug_dag: bool = False
    verbose: bool = False
    show_failed_logs: bool = False
    stdout: bool = False
    dryrun: bool = False


def _make_handler(batch_size=50, flush_interval=2.0, mock_post=None) -> LogHandler:
    settings = LoggerSettings(
        url="http://test.invalid",
        batch_size=batch_size,
        flush_interval=flush_interval,
    )
    common = _CommonSettings()
    with patch("httpx.Client") as ClientCls:
        client = MagicMock()
        if mock_post is not None:
            client.post.side_effect = mock_post
        else:
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            client.post.return_value = resp
        ClientCls.return_value = client
        h = LogHandler(common_settings=common, settings=settings)
    h._client = client  # ensure we hold the same mock
    # The handler emits a synthetic WORKFLOW_STARTED on init; drop it
    # so tests can reason about a clean buffer.
    h._buffer.clear()
    return h


def _record(event_name: str, **extra) -> logging.LogRecord:
    rec = logging.LogRecord(
        name="snakemake", level=logging.INFO, pathname="", lineno=0,
        msg="", args=None, exc_info=None,
    )
    rec.__dict__["event"] = type("E", (), {"value": event_name})()
    rec.__dict__.update(extra)
    return rec


def test_size_threshold_triggers_flush():
    h = _make_handler(batch_size=3, flush_interval=999)
    try:
        for jid in [1, 2]:
            h.emit(_record("job_finished", job_id=jid))
        # 2 events, no flush yet
        assert h._client.post.call_count == 0
        h.emit(_record("job_finished", job_id=3))
        # crossing batch_size triggers flush
        assert h._client.post.call_count == 1
        # buffer drained
        assert h._buffer == []
    finally:
        h.close()


def test_interval_triggers_flush():
    h = _make_handler(batch_size=999, flush_interval=0.05)
    try:
        h.emit(_record("job_finished", job_id=42))
        # wait at least one tick
        deadline = time.time() + 2.0
        while time.time() < deadline and h._client.post.call_count == 0:
            time.sleep(0.05)
        assert h._client.post.call_count >= 1
    finally:
        h.close()


def test_retry_then_continue_on_failure():
    calls = {"n": 0}

    def flaky(_url, json):
        calls["n"] += 1
        raise httpx.ConnectError("boom")

    h = _make_handler(batch_size=1, flush_interval=999, mock_post=flaky)
    try:
        h.emit(_record("job_finished", job_id=1))
        # Each emit-triggered flush retries 4 times (1 initial + 3 backoff).
        # Plugin should not raise; events are re-buffered for next flush.
        assert calls["n"] == 4
        assert len(h._buffer) == 1
    finally:
        h.close()


def test_job_started_fans_out_per_jobid():
    h = _make_handler(batch_size=999, flush_interval=999)
    try:
        h.emit(_record("job_started", jobs=[10, 11, 12]))
        assert len(h._buffer) == 3
        assert {e["internal_id"] for e in h._buffer} == {10, 11, 12}
    finally:
        h.close()


def test_synthesizes_startup_and_completion():
    """Plugin must emit WORKFLOW_STARTED at init and WORKFLOW_DONE at close.

    Snakemake 9.x doesn't reliably emit either to logger plugins, so the
    plugin synthesizes them from Python introspection (version, cwd) and
    on close().
    """
    h = _make_handler(batch_size=999, flush_interval=999)
    # Don't use _make_handler's clear() here — re-create directly to keep
    # the startup event around.
    settings = LoggerSettings(url="http://test.invalid", batch_size=999, flush_interval=999)
    common = _CommonSettings()
    with patch("httpx.Client") as ClientCls:
        client = MagicMock()
        resp = MagicMock(); resp.raise_for_status.return_value = None
        client.post.return_value = resp
        ClientCls.return_value = client
        fresh = LogHandler(common_settings=common, settings=settings)
    fresh._client = client
    try:
        events = list(fresh._buffer)
        assert events and events[0]["event"] == "WORKFLOW_STARTED"
        assert events[0]["snakemake_version"]  # whatever version is installed
        assert events[0]["cwd"]  # always available
    finally:
        fresh.close()
    # close() should have appended a WORKFLOW_DONE before flushing.
    posted_payloads = [c.kwargs["json"] for c in client.post.call_args_list]
    all_event_names = [e["event"] for p in posted_payloads for e in p["events"]]
    assert "WORKFLOW_DONE" in all_event_names
    h.close()


def test_rulegraph_event_forwarded():
    """Snakemake 9.x nests the topology under `rulegraph` with key
    `links` (not `edges`); plugin must unwrap and rewire."""
    h = _make_handler(batch_size=999, flush_interval=999)
    try:
        h.emit(_record(
            "rulegraph",
            rulegraph={
                "nodes": [{"rule": "a"}, {"rule": "b"}],
                "links": [{"source": 0, "target": 1,
                           "sourcerule": "a", "targetrule": "b"}],
            },
        ))
        assert len(h._buffer) == 1
        ev = h._buffer[0]
        assert ev["event"] == "RULEGRAPH"
        assert ev["nodes"] == [{"rule": "a"}, {"rule": "b"}]
        assert ev["edges"] == [{"source": 0, "target": 1}]
    finally:
        h.close()


def test_unforwarded_event_dropped():
    h = _make_handler(batch_size=999, flush_interval=999)
    try:
        h.emit(_record("shellcmd", shellcmd="echo hi"))
        h.emit(_record("group_info"))
        assert h._buffer == []
    finally:
        h.close()
