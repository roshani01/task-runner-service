"""
Shared test fixtures.

Tests use a real PostgreSQL database (the same one configured in .env).
We create a fresh schema for each test session and truncate tables between tests.
This is simpler and more realistic than mocking the DB layer.

Set TEST_DATABASE_URL in .env or environment to override.
"""  
import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.main import app
from app.services.scheduler import get_semaphore

# Allow overriding DB for CI
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://task_runner:task_runner_password@localhost:5432/task_runner",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(test_engine):
    """Truncate all tables before each test for isolation."""
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE task_attempts, task_dependencies, tasks RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncSession:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_engine, monkeypatch) -> AsyncClient:
    """
    HTTP client wired to the FastAPI app.
    We override the DB engine so tests use the test database,
    and disable the scheduler background loop.
    """
    from app.core import database as db_module

    monkeypatch.setattr(db_module, "engine", test_engine)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "AsyncSessionLocal", factory)

    # Don't run the real scheduler in tests — tests control execution manually
    import app.main as main_module
    monkeypatch.setattr(main_module, "on_startup", lambda: None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
