"""In-process pub/sub for live (SSE) project events — job progress, director actions.

A simple ``project_id -> set[Queue]`` fan-out. This is correct ONLY because the app runs a
single uvicorn worker (see Dockerfile); a multi-worker move must swap this for Redis pub/sub
so events reach every worker. SSE is purely additive — the reconciler + 5s poll remain the
source of truth, so a dropped/slow event is harmless (we never block a producer on it).
"""

import asyncio
import json
from collections import defaultdict

_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def subscribe(project_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[project_id].add(q)
    return q


def unsubscribe(project_id: str, q: asyncio.Queue) -> None:
    subs = _subscribers.get(project_id)
    if subs is not None:
        subs.discard(q)
        if not subs:
            _subscribers.pop(project_id, None)


def publish(project_id: str, event: dict) -> None:
    """Fan an event out to every subscriber. Never blocks: a full (slow) consumer queue
    drops the event rather than stalling the producer — the poll fallback will catch up."""
    for q in list(_subscribers.get(project_id, ())):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


def sse(event: dict) -> str:
    """Format one event as an SSE ``data:`` frame."""
    return f"data: {json.dumps(event)}\n\n"
