"""Test fixtures. API tests run against the Railway Postgres test DB (TEST_DATABASE_URL)
when configured, else an in-memory SQLite fallback. The LLM is always mocked
(USE_MOCK_LLM=true), so the only external dependency is the test database.

Each test gets a fresh schema (create_all on entry, drop_all on exit) and its own engine
bound to the test's event loop — avoiding asyncpg cross-loop issues.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (register tables on metadata)
from app.core.config import get_settings
from app.core.db import get_session
from app.main import app


def _test_db_url() -> str:
    return get_settings().test_database_url or "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def client():
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
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()
