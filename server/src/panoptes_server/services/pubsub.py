"""In-process pub/sub bus, keyed by workflow_id.

The ingest path publishes a small JSON delta after every committed
batch; WebSocket subscribers receive it on their per-connection
asyncio.Queue. This is "pub/sub" only in the simplest sense — a
single FastAPI process. The day someone needs multi-replica
panoptes, the bus's `publish`/`subscribe` API can be re-implemented
on top of Redis pub/sub without touching callers.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)

# Bounded so a slow/wedged subscriber can't grow unboundedly. If a
# subscriber falls behind, we drop the oldest messages — the client
# will refetch on its polling interval anyway.
_QUEUE_MAXSIZE = 64

_subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
_lock = asyncio.Lock()


async def subscribe(workflow_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    async with _lock:
        _subscribers[workflow_id].add(q)
    return q


async def unsubscribe(workflow_id: int, q: asyncio.Queue) -> None:
    async with _lock:
        _subscribers[workflow_id].discard(q)
        if not _subscribers[workflow_id]:
            _subscribers.pop(workflow_id, None)


async def publish(workflow_id: int, message: dict[str, Any]) -> int:
    """Fan out `message` to every subscriber of `workflow_id`.

    Returns the number of subscribers reached. Slow subscribers whose
    queue is full have their oldest message dropped to make room —
    correctness is preserved because clients already refetch on
    polling tick as a safety net.
    """
    async with _lock:
        targets = list(_subscribers.get(workflow_id, ()))

    delivered = 0
    for q in targets:
        try:
            q.put_nowait(message)
            delivered += 1
        except asyncio.QueueFull:
            try:
                _ = q.get_nowait()
                q.put_nowait(message)
                delivered += 1
            except Exception:  # pragma: no cover — defensive
                log.warning("pubsub: dropped message for wf=%d", workflow_id)
    return delivered


def subscriber_count(workflow_id: int) -> int:
    return len(_subscribers.get(workflow_id, ()))
