"""
Tests for Agent Tool Dispatcher and Concrete Handlers.
Validates all 6 tool contracts, Pydantic argument validation,
database retrieval, Hindsight memory recall, and Band room messaging.
"""

import asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.db.repository import SQLAlchemyRepository
from backend.app.services.band_adapter import MockBandAdapter
from backend.app.services.hindsight_service import HindsightService
from backend.app.services.tool_handlers import AgentToolDispatcher


@pytest.fixture
def test_dispatcher():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session = session_factory()
        repo = SQLAlchemyRepository(session)
        await repo.seed_demo_data()

        hindsight = HindsightService(api_key=None)  # Offline fallback
        band = MockBandAdapter(room_prefix="test-war-room")
        dispatcher = AgentToolDispatcher(db_repo=repo, hindsight=hindsight, band=band)
        return engine, session, dispatcher, band

    return _setup


def test_tool_recall_similar_incidents(test_dispatcher):
    async def _test():
        engine, session, dispatcher, _ = await test_dispatcher()
        try:
            # Valid tool call
            res = await dispatcher.execute_tool(
                "recall_similar_incidents",
                {"service_name": "checkout-api", "symptom": "Connection pool full", "limit": 3},
            )
            assert res["tool"] == "recall_similar_incidents"
            assert res["count"] >= 1
            assert res["similar_incidents"][0]["incident_id"] == "INC-1987"

            # Invalid argument: limit < 1
            inv = await dispatcher.execute_tool(
                "recall_similar_incidents",
                {"service_name": "checkout-api", "symptom": "500", "limit": 0},
            )
            assert "error" in inv
            assert "Validation error" in inv["error"]
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_tool_recall_failed_fixes(test_dispatcher):
    async def _test():
        engine, session, dispatcher, _ = await test_dispatcher()
        try:
            res = await dispatcher.execute_tool(
                "recall_failed_fixes",
                {"service_name": "payments-db", "incident_signature": "ConnectionPoolExhausted"},
            )
            assert res["tool"] == "recall_failed_fixes"
            assert res["count"] >= 1
            assert "Do NOT restart payments-db" in res["failed_fixes"][0]["warning_directive"]

            # Missing required field 'incident_signature'
            inv = await dispatcher.execute_tool("recall_failed_fixes", {"service_name": "payments-db"})
            assert "error" in inv
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_tool_get_recent_deploys(test_dispatcher):
    async def _test():
        engine, session, dispatcher, _ = await test_dispatcher()
        try:
            res = await dispatcher.execute_tool(
                "get_recent_deploys",
                {"service_name": "checkout-api", "lookback_hours": 48},
            )
            assert res["tool"] == "get_recent_deploys"
            assert res["count"] >= 1
            assert res["deploys"][0]["service_name"] == "checkout-api"
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_tool_get_logs(test_dispatcher):
    async def _test():
        engine, session, dispatcher, _ = await test_dispatcher()
        try:
            res = await dispatcher.execute_tool(
                "get_logs",
                {"service_name": "checkout-api", "incident_id": "INC-2045", "limit": 20},
            )
            assert res["tool"] == "get_logs"
            assert res["count"] >= 1
            assert any("ConnectionPoolExhausted" in l["message"] for l in res["logs"])
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_tool_get_service_owner(test_dispatcher):
    async def _test():
        engine, session, dispatcher, _ = await test_dispatcher()
        try:
            res = await dispatcher.execute_tool(
                "get_service_owner",
                {"service_name": "checkout-api"},
            )
            assert res["tool"] == "get_service_owner"
            assert "@priya" in res["owner"]
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_tool_post_to_band_room(test_dispatcher):
    async def _test():
        engine, session, dispatcher, band = await test_dispatcher()
        try:
            res = await dispatcher.execute_tool(
                "post_to_band_room",
                {"incident_id": "INC-2045", "message": "Investigating connection pool leak", "sender": "Lead SRE"},
            )
            assert res["tool"] == "post_to_band_room"
            assert res["delivered"] is True
            assert len(band.messages_posted) == 1
            assert band.messages_posted[0]["sender"] == "Lead SRE"
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_tool_unknown_name(test_dispatcher):
    async def _test():
        engine, session, dispatcher, _ = await test_dispatcher()
        try:
            res = await dispatcher.execute_tool("drop_database", {})
            assert "error" in res
            assert "Unknown tool" in res["error"]
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())
