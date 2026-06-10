"""Proactive provider rate limiter — sliding window + min spacing, waits outside the lock."""

import asyncio
import time

import pytest

from app.core.rate_limit import SlidingWindowLimiter


@pytest.mark.asyncio
async def test_unlimited_when_rpm_zero():
    limiter = SlidingWindowLimiter(0)
    start = time.monotonic()
    for _ in range(50):
        await limiter.acquire()
    assert time.monotonic() - start < 0.5


@pytest.mark.asyncio
async def test_min_spacing_between_acquisitions():
    # rpm=600 -> min spacing 0.1s; 3 acquisitions need >= 0.2s total
    limiter = SlidingWindowLimiter(600)
    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    assert time.monotonic() - start >= 0.18


@pytest.mark.asyncio
async def test_concurrent_acquirers_are_serialized_not_deadlocked():
    limiter = SlidingWindowLimiter(1200)  # 0.05s spacing
    start = time.monotonic()
    await asyncio.gather(*(limiter.acquire() for _ in range(4)))
    elapsed = time.monotonic() - start
    assert elapsed >= 0.12  # 3 gaps x 0.05s, allowing scheduler slack
    assert elapsed < 2.0
