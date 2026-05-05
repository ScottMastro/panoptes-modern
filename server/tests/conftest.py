import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["PANOPTES_DB_URL"] = "sqlite+aiosqlite:///:memory:"

from panoptes_server import db  # noqa: E402
from panoptes_server.main import create_app  # noqa: E402


@pytest_asyncio.fixture
async def app():
    await db.reset_engine("sqlite+aiosqlite:///:memory:")
    await db.create_all()
    application = create_app()
    try:
        yield application
    finally:
        if db._engine is not None:
            await db._engine.dispose()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
