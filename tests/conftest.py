# tests/conftest.py
# Shared test configuration for all API test modules.
# Uses a single in-memory SQLite engine with StaticPool to ensure
# the same database is shared across all async sessions within a test.

import pytest
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.pool import StaticPool

from api.main import app
from api.db import get_session

# Single shared in-memory async SQLite engine
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

async def override_get_session():
    async with AsyncSession(test_engine) as session:
        yield session

# Apply the override once for all tests
app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(autouse=True)
async def setup_db():
    """Create tables before each test, drop after. Ensures test isolation."""
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
