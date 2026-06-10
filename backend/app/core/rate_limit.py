"""Proactive provider rate limiting — pace submits instead of absorbing 429s.

A process-wide sliding-window limiter keyed by service ("video", "image"). Semantics
follow ViMax's limiter (rpm window + minimum inter-request spacing) but the waiting is
done OUTSIDE the lock so one throttled caller never serializes everyone else
(docs/vimax-research.md §3 A8). Reactive 429 retry in ``core.http`` stays as the backstop.
"""

import asyncio
import time
from collections import deque

from app.core.config import get_settings


class SlidingWindowLimiter:
    """Allow at most ``rpm`` acquisitions per rolling 60s, spaced >= 60/rpm apart."""

    def __init__(self, rpm: int):
        self.rpm = rpm
        self.min_spacing = 60.0 / rpm if rpm > 0 else 0.0
        self._times: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.rpm <= 0:  # 0 = unlimited
            return
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._times and now - self._times[0] >= 60.0:
                    self._times.popleft()
                wait = 0.0
                if self._times:
                    wait = max(wait, self._times[-1] + self.min_spacing - now)
                if len(self._times) >= self.rpm:
                    wait = max(wait, self._times[0] + 60.0 - now)
                if wait <= 0:
                    self._times.append(now)
                    return
            # compute under lock, sleep outside it, then re-check
            await asyncio.sleep(wait)


_limiters: dict[str, SlidingWindowLimiter] = {}


def _limiter_for(service: str) -> SlidingWindowLimiter:
    if service not in _limiters:
        settings = get_settings()
        rpm = {"video": settings.video_rpm, "image": settings.image_rpm}.get(service, 0)
        _limiters[service] = SlidingWindowLimiter(rpm)
    return _limiters[service]


async def acquire(service: str) -> None:
    """Block until a request slot for ``service`` is available."""
    await _limiter_for(service).acquire()
