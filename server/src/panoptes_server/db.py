import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

DEFAULT_DB_URL = "sqlite+aiosqlite:///./panoptes.db"

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _db_url() -> str:
    return os.environ.get("PANOPTES_DB_URL", DEFAULT_DB_URL)


def init_engine(url: str | None = None) -> None:
    """Configure the module-level engine. Idempotent for the same URL."""
    global _engine, _sessionmaker
    target = url or _db_url()
    if _engine is not None:
        return
    _engine = create_async_engine(target, echo=False, future=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


async def reset_engine(url: str | None = None) -> None:
    """Tear down and reinitialize. Used by tests."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
    init_engine(url)


async def create_all() -> None:
    assert _engine is not None, "init_engine must be called first"
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    assert _sessionmaker is not None, "init_engine must be called first"
    async with _sessionmaker() as session:
        yield session
