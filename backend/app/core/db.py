"""Async database engine, session factory, and FastAPI session dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.core.config import get_settings

_settings = get_settings()

# create_async_engine does not open a connection until first use, so importing this module
# is safe even when the database is unreachable.
engine = create_async_engine(_settings.db_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables. Importing app.models populates SQLModel.metadata."""
    import app.models  # noqa: F401  (registers all table classes)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
