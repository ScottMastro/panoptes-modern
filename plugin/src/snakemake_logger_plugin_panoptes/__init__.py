"""Snakemake logger plugin that ships LogEvents to a panoptes server.

Subscribes to the snakemake-interface-logger-plugins LogEvent stream,
buffers events, and POSTs batches to /api/v1/ingest. Connection
failures are retried; final failure is logged but does not crash the
snakemake run.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from snakemake_interface_logger_plugins.base import LogHandlerBase
from snakemake_interface_logger_plugins.common import LogEvent

from snakemake_logger_plugin_panoptes.settings import LoggerSettings

# The plugin registry discovers settings under this exact name.
LogHandlerSettings = LoggerSettings

__all__ = ["LogHandler", "LogHandlerSettings", "LoggerSettings"]


# Events we forward to the server. Other LogEvents (SHELLCMD, GROUP_*,
# DEBUG_DAG, RESOURCES_INFO, RULEGRAPH) are ignored in v1.
_FORWARDED = {
    LogEvent.WORKFLOW_STARTED.value,
    LogEvent.RUN_INFO.value,
    LogEvent.JOB_INFO.value,
    LogEvent.JOB_STARTED.value,
    LogEvent.JOB_FINISHED.value,
    LogEvent.JOB_ERROR.value,
    LogEvent.PROGRESS.value,
    LogEvent.RULEGRAPH.value,
}


def _ts(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe(obj: Any) -> Any:
    """Best-effort JSON-serializable coercion of arbitrary extras."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _record_to_events(record: logging.LogRecord) -> list[dict]:
    """Translate one LogRecord into 0+ ingest event dicts.

    JOB_STARTED arrives with a *list* of jobids; we fan it out into one
    event per jobid so the server's per-job upsert sees them
    individually.
    """
    raw = record.__dict__.get("event")
    if raw is None:
        return []
    name = raw.value if hasattr(raw, "value") else str(raw)
    if name not in _FORWARDED:
        return []

    ts = _ts(record)
    d = record.__dict__

    if name == LogEvent.WORKFLOW_STARTED.value:
        return [
            {
                "event": "WORKFLOW_STARTED",
                "ts": ts,
                "snakefile": d.get("snakefile"),
                "snakemake_version": _snakemake_version(),
            }
        ]

    if name == LogEvent.RUN_INFO.value:
        stats = d.get("stats")
        total = None
        if isinstance(stats, dict):
            total = stats.get("total_jobs") or stats.get("total")
        return [
            {
                "event": "RUN_INFO",
                "ts": ts,
                "total_jobs": total,
                "detail": {"stats": _safe(stats)} if stats is not None else None,
            }
        ]

    if name == LogEvent.PROGRESS.value:
        return [
            {
                "event": "PROGRESS",
                "ts": ts,
                "done": d.get("done"),
                "total": d.get("total"),
            }
        ]

    if name == LogEvent.JOB_INFO.value:
        return [
            {
                "event": "JOB_INFO",
                "ts": ts,
                "internal_id": d.get("jobid"),
                "rule": d.get("rule_name"),
                "wildcards": _safe(d.get("wildcards")),
                "threads": d.get("threads"),
                "log": _first(d.get("log")),
            }
        ]

    if name == LogEvent.JOB_STARTED.value:
        jobs = d.get("jobs") or []
        if not isinstance(jobs, (list, tuple)):
            jobs = [jobs]
        return [
            {"event": "JOB_STARTED", "ts": ts, "internal_id": jid} for jid in jobs
        ]

    if name == LogEvent.JOB_FINISHED.value:
        return [
            {
                "event": "JOB_FINISHED",
                "ts": ts,
                "internal_id": d.get("job_id") if d.get("job_id") is not None else d.get("jobid"),
            }
        ]

    if name == LogEvent.RULEGRAPH.value:
        # Snakemake 9.x emits the topology nested under `rulegraph`,
        # with keys `nodes` and `links` (not `edges`). Each edge has
        # numeric `source`/`target` indices plus convenience
        # `sourcerule`/`targetrule` names — keep the names in detail
        # but normalize the wire shape to `nodes` + `edges`.
        rg = d.get("rulegraph")
        if not isinstance(rg, dict):
            return []
        nodes = rg.get("nodes")
        links = rg.get("links") or rg.get("edges")
        if not isinstance(nodes, list) or not isinstance(links, list):
            return []
        return [{
            "event": "RULEGRAPH",
            "ts": ts,
            "nodes": [_safe(n) for n in nodes],
            "edges": [
                {
                    "source": e.get("source"),
                    "target": e.get("target"),
                } for e in links if isinstance(e, dict)
            ],
        }]

    if name == LogEvent.JOB_ERROR.value:
        return [
            {
                "event": "JOB_ERROR",
                "ts": ts,
                "internal_id": d.get("jobid"),
                "rule": d.get("rule_name"),
                "log": _first(d.get("log")),
            }
        ]

    return []


def _first(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return str(value)


def _snakemake_version() -> Optional[str]:
    try:
        from snakemake import __version__
        return __version__
    except Exception:
        return None


class LogHandler(LogHandlerBase):
    """Buffered HTTP forwarder for snakemake LogEvents.

    The handler is a logging.Handler, so emit() runs on whichever
    thread snakemake logs from. We append to an in-memory buffer under
    a lock; a daemon thread flushes every flush_interval, and emit()
    flushes synchronously when the buffer crosses batch_size.
    """

    def __init__(self, *args, **kwargs) -> None:
        # LogHandlerBase doesn't chain into logging.Handler.__init__,
        # so we have to do it ourselves before close() can run.
        logging.Handler.__init__(self)
        super().__init__(*args, **kwargs)
        if self.settings is None or not getattr(self.settings, "url", None):
            raise ValueError(
                "panoptes logger plugin requires --logger-panoptes-url"
            )
        self._url = self.settings.url.rstrip("/") + "/api/v1/ingest"
        self._batch_size: int = int(self.settings.batch_size)
        self._flush_interval: float = float(self.settings.flush_interval)
        self._run_id = str(uuid.uuid4())
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._client = httpx.Client(timeout=10.0)
        self._flush_thread = threading.Thread(
            target=self._flush_loop, name="panoptes-flush", daemon=True
        )
        self._flush_thread.start()

        # Snakemake 9.x doesn't reliably emit WORKFLOW_STARTED to logger
        # plugins, so synthesize a startup event from Python introspection
        # — version, cwd, snakefile path. This populates the workflow row
        # immediately and avoids relying on a snakemake event that may not
        # arrive.
        self._enqueue_startup_event()
        self._closed = False

    # --- LogHandlerBase contract ------------------------------------------------

    @property
    def writes_to_stream(self) -> bool:
        return False

    @property
    def writes_to_file(self) -> bool:
        return False

    @property
    def has_filter(self) -> bool:
        return False

    @property
    def has_formatter(self) -> bool:
        return False

    @property
    def needs_rulegraph(self) -> bool:
        return True

    # --- logging.Handler contract -----------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            events = _record_to_events(record)
        except Exception as e:  # never crash snakemake
            print(f"[panoptes] skipped malformed log record: {e}", file=sys.stderr)
            return
        if not events:
            return
        with self._lock:
            self._buffer.extend(events)
            should_flush = len(self._buffer) >= self._batch_size
        if should_flush:
            self._flush_once()

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        # Synthesize WORKFLOW_DONE — snakemake 9.x doesn't reliably emit it.
        # The server's completion-fallback logic also covers the case where
        # this plugin is killed mid-run.
        try:
            self._enqueue_completion_event()
        except Exception:
            pass
        self._stop.set()
        try:
            self._flush_thread.join(timeout=self._flush_interval + 1.0)
        except Exception:
            pass
        self._flush_once()
        try:
            self._client.close()
        except Exception:
            pass
        super().close()

    def _enqueue_startup_event(self) -> None:
        snakefile = self._guess_snakefile()
        event = {
            "event": "WORKFLOW_STARTED",
            "ts": _now_iso(),
            "snakemake_version": _snakemake_version(),
            "cwd": os.getcwd(),
            "snakefile": snakefile,
        }
        with self._lock:
            self._buffer.append(event)

    def _enqueue_completion_event(self) -> None:
        event = {"event": "WORKFLOW_DONE", "ts": _now_iso()}
        with self._lock:
            self._buffer.append(event)

    @staticmethod
    def _guess_snakefile() -> Optional[str]:
        # The conventional names; if none exist we leave it null.
        for name in ("Snakefile", "Snakefile.smk", "workflow/Snakefile"):
            if os.path.isfile(name):
                return os.path.abspath(name)
        return None

    # --- flushing ---------------------------------------------------------------

    def _flush_loop(self) -> None:
        while not self._stop.wait(self._flush_interval):
            self._flush_once()

    def _flush_once(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            payload = {"run_id": self._run_id, "events": self._buffer}
            self._buffer = []
        if not self._post(payload):
            # Re-buffer events at the front so the next flush retries
            # them. New events are appended after, preserving order.
            with self._lock:
                self._buffer = payload["events"] + self._buffer

    def _post(self, payload: dict) -> bool:
        delays = (0.5, 1.0, 2.0)
        for i, delay in enumerate((0.0,) + delays):
            if delay:
                time.sleep(delay)
            try:
                resp = self._client.post(self._url, json=payload)
                resp.raise_for_status()
                return True
            except (httpx.HTTPError, OSError) as e:
                if i == len(delays):
                    print(
                        f"[panoptes] failed to ship {len(payload['events'])} "
                        f"events to {self._url}: {e}",
                        file=sys.stderr,
                    )
        return False
