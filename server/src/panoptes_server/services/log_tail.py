"""Tail a job's log file, with path-traversal sandboxing.

`Job.log_path` ultimately came from snakemake's own logger record so
it's not directly attacker-supplied — but treating it as untrusted
is free insurance against the day someone exposes panoptes over the
network. We refuse to read anything outside the workflow's `cwd`.
"""
from __future__ import annotations

import os
from collections import deque
from pathlib import Path

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB hard cap


class LogAccessError(Exception):
    """Raised when a log path can't or shouldn't be read."""


def _validate_path(log_path: str, cwd: str | None) -> Path:
    if not log_path:
        raise LogAccessError("no log path on this job")
    raw = Path(log_path)
    # Snakemake stores log paths as the raw `log:` directive value,
    # often relative to the workflow's cwd. Resolve against cwd when
    # the path is relative; reject anything that escapes cwd.
    if not raw.is_absolute() and cwd:
        raw = Path(cwd) / raw
    p = raw.resolve(strict=False)
    if not p.is_file():
        raise LogAccessError("log file not found")
    if cwd:
        cwd_resolved = Path(cwd).resolve(strict=False)
        try:
            p.relative_to(cwd_resolved)
        except ValueError as e:
            raise LogAccessError(
                "log path escapes the workflow's working directory"
            ) from e
    return p


def tail_log(log_path: str, cwd: str | None, max_lines: int = 200) -> dict:
    p = _validate_path(log_path, cwd)
    size = p.stat().st_size
    if size > MAX_FILE_BYTES:
        # Big file: seek-from-end so we don't read 10 GB of cluster logs.
        with p.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            buf = b""
            block = 8192
            while fh.tell() > 0 and buf.count(b"\n") <= max_lines:
                step = min(block, fh.tell())
                fh.seek(-step, os.SEEK_CUR)
                buf = fh.read(step) + buf
                fh.seek(-step, os.SEEK_CUR)
            text = buf.decode("utf-8", errors="replace")
        lines = text.splitlines()[-max_lines:]
        truncated = True
    else:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=max_lines)
        lines = [line.rstrip("\n") for line in tail]
        truncated = (
            sum(1 for _ in p.open("r", encoding="utf-8", errors="replace"))
            > max_lines
        )

    return {
        "path": str(p),
        "lines": lines,
        "truncated": truncated,
        "size_bytes": size,
    }
