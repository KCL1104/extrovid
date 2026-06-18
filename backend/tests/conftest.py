"""Test fixtures. API tests run against the Railway Postgres test DB (TEST_DATABASE_URL)
when configured, else an in-memory SQLite fallback. The LLM is always mocked
(USE_MOCK_LLM=true), so the only external dependency is the test database.

Each test gets a fresh schema (create_all on entry, drop_all on exit) and its own engine
bound to the test's event loop — avoiding asyncpg cross-loop issues.

Two clients:
- ``client`` overrides ``current_auth`` with a non-admin test user (caps mirrored from
  settings so the cap fixtures keep working) — used by the functional suite.
- ``raw_client`` leaves the real auth gate in place — used by the auth / multi-tenancy tests,
  which register real users and pass real Bearer tokens.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (register tables on metadata)
from app.core.auth import AuthCtx, current_auth
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app


def _test_db_url() -> str:
    return get_settings().test_database_url or "sqlite+aiosqlite://"


def _fake_auth() -> AuthCtx:
    # A non-admin test user; caps follow settings so daily_*_cap fixtures still drive the gate.
    s = get_settings()
    return AuthCtx(
        user=None,
        is_admin=False,
        user_id="test-user",
        video_cap=s.daily_video_cap,
        image_cap=s.daily_image_cap,
        audio_cap=s.daily_audio_cap,
    )


async def _client_gen(override_auth: bool):
    url = _test_db_url()
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}

    engine = create_async_engine(url, **kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    test_session = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_session():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    if override_auth:
        app.dependency_overrides[current_auth] = _fake_auth

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()


@pytest_asyncio.fixture
async def client():
    async for ac in _client_gen(override_auth=True):
        yield ac


@pytest_asyncio.fixture
async def raw_client():
    async for ac in _client_gen(override_auth=False):
        yield ac
