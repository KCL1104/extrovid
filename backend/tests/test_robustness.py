"""Robustness: provider retry/backoff, stuck-job timeout, bucket cleanup on delete."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.http import request_with_retry
from app.models.generation import GenerationJob
from app.providers.video_factory import PollResult
from app.services import generate_service


@pytest.fixture
def fast_retry():
    s = get_settings()
    prev = s.http_retry_base_sec
    s.http_retry_base_sec = 0.0
    yield
    s.http_retry_base_sec = prev


async def test_retry_then_success(fast_retry):
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return httpx.Response(503 if calls["n"] == 1 else 200, text="ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        r = await request_with_retry("GET", "https://x/y", client=client)
        assert r.status_code == 200
        assert calls["n"] == 2  # one 503, then success
    finally:
        await client.aclose()


async def test_retry_gives_up_returns_last(fast_retry):
    s = get_settings()
    prev = s.http_max_retries
    s.http_max_retries = 2
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        r = await request_with_retry("GET", "https://x/y", client=client)
        assert r.status_code == 503
        assert calls["n"] == 3  # 1 initial + 2 retries
    finally:
        await client.aclose()
        s.http_max_retries = prev


async def test_stuck_job_times_out(monkeypatch):
    async def fake_poll(_task_id):
        return PollResult(status="RUNNING")

    monkeypatch.setattr(generate_service, "poll_video", fake_poll)
    s = get_settings()
    prev_to, prev_mock = s.video_job_timeout_sec, s.use_mock_video
    s.video_job_timeout_sec = 0
    s.use_mock_video = False

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as c:
        await c.run_sync(SQLModel.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as session:
            job = GenerationJob(
                shot_version_id="x",
                status="running",
                task_id="real-task-123",
                started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=30),
            )
            session.add(job)
            await session.commit()
            out = await generate_service.poll_and_ingest_job(session, job)
            assert out.status == "failed"
            assert out.failure_reason == "timed out"
    finally:
        s.video_job_timeout_sec, s.use_mock_video = prev_to, prev_mock
        await engine.dispose()


async def test_delete_project_cleans_bucket_objects(client):
    from app.services.asset_service import _MOCK_STORE

    pid = (await client.post("/api/projects", json={"title": "Clean"})).json()["id"]
    await client.post(f"/api/projects/{pid}/run", json={"raw_prompt": "a 20s teaser"})
    cs = (await client.get(f"/api/projects/{pid}/concept-sets")).json()[0]["id"]
    await client.post(f"/api/projects/{pid}/concept-sets/{cs}/generate-images")

    before = [k for k in _MOCK_STORE if k.startswith(pid + "/")]
    assert before  # concept images were stored

    await client.delete(f"/api/projects/{pid}")
    after = [k for k in _MOCK_STORE if k.startswith(pid + "/")]
    assert after == []  # bucket objects cleaned up
