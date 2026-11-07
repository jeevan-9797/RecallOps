"""
Pytest Global Test Configuration and Fixtures for RecallOps.
Configures test databases, FastAPI TestClient dependency overrides, and isolation.
"""

import asyncio
from typing import AsyncGenerator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.repository import SQLAlchemyRepository
from backend.app.db.session import get_db_session
from backend.app.main import app


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
def test_db_session_factory():
    """Creates a fresh, shared in-memory SQLite database populated with standard demo data."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            repo = SQLAlchemyRepository(session)
            await repo.seed_demo_data()
        return engine, session_factory

    return _setup


@pytest.fixture
def client(test_db_session_factory):
    """Provides a TestClient with get_db_session overridden to use the seeded test database."""
    engine, session_factory = asyncio.run(test_db_session_factory())

    async def override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    from unittest.mock import patch

    app.dependency_overrides[get_db_session] = override_get_db_session
    with patch("backend.app.services.groq_agent.GroqAgent._get_client", return_value=None), \
         patch("backend.app.services.hindsight_service.hindsight_service._get_client", return_value=None):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
