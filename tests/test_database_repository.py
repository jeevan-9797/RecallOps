"""
Tests for RecallOps Database Layer and SQLAlchemy Repository.
Runs on an async in-memory SQLite engine to verify schemas, relations, and repository queries.
"""

import asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.db.repository import SQLAlchemyRepository


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def async_repo():
    """Initializes in-memory database and provides an active repository instance."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session = session_factory()
        repo = SQLAlchemyRepository(session)
        return engine, session, repo

    return _setup


def test_seed_and_query_services(async_repo):
    async def _test():
        engine, session, repo = await async_repo()
        try:
            # Seed standard Kartly demo data
            seed_res = await repo.seed_demo_data()
            assert seed_res["services_seeded"] == 6
            assert seed_res["engineers_seeded"] == 8
            assert seed_res["deploys_seeded"] == 3

            # Query service
            svc = await repo.get_service("checkout-api")
            assert svc is not None
            assert svc["name"] == "checkout-api"
            assert "Payment" in svc["owner_team"]
            assert svc["tier"] == "tier-1"

            # Query non-existent service
            missing = await repo.get_service("ghost-service")
            assert missing is None
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_get_service_owner(async_repo):
    async def _test():
        engine, session, repo = await async_repo()
        try:
            await repo.seed_demo_data()

            # Should return on-call engineer Priya Sharma (@priya.sharma)
            owner = await repo.get_service_owner("checkout-api")
            assert owner is not None
            assert "@priya" in owner

            # Unassigned service returns team fallback
            fallback = await repo.get_service_owner("notification-service")
            assert "notification-service" in fallback or "squad" in fallback
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_get_service_owner_engineer(async_repo):
    async def _test():
        engine, session, repo = await async_repo()
        try:
            await repo.seed_demo_data()

            # Should return structured Engineer dictionary for checkout-api owner (Priya Sharma)
            eng = await repo.get_service_owner_engineer("checkout-api")
            assert eng is not None
            assert eng["id"] == 4
            assert eng["name"] == "Priya Sharma"
            assert eng["handle"] == "priya"
            assert eng["slack_handle"] == "@priya.sharma"
            assert eng["service_name"] == "checkout-api"

            # Should return Diya for orders-worker
            diya = await repo.get_service_owner_engineer("orders-worker")
            assert diya is not None
            assert diya["handle"] == "diya"
            assert diya["id"] == 2

            # Non-existent service returns None
            missing = await repo.get_service_owner_engineer("non-existent-service")
            assert missing is None
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_deploys_and_logs_queries(async_repo):
    async def _test():
        engine, session, repo = await async_repo()
        try:
            await repo.seed_demo_data()

            # Deploys query with lookback
            deploys = await repo.get_recent_deploys("checkout-api", lookback_hours=48)
            assert len(deploys) >= 1
            assert deploys[0]["service_name"] == "checkout-api"
            assert "DEP-" in deploys[0]["deploy_id"]

            # Logs query for INC-2045
            logs = await repo.get_logs("checkout-api", "INC-2045", limit=10)
            assert len(logs) >= 4
            assert any("ConnectionPoolExhausted" in l["message"] for l in logs)
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_incident_lifecycle(async_repo):
    async def _test():
        engine, session, repo = await async_repo()
        try:
            await repo.seed_demo_data()

            # 1. Create incident
            inc_id = await repo.create_incident("payments-db", "Deadlock detected on transactions table", "CRITICAL")
            assert inc_id.startswith("INC-")

            inc = await repo.get_incident(inc_id)
            assert inc is not None
            assert inc["status"] in ("open", "created")
            assert inc["service_name"] == "payments-db"

            # 2. Record fix attempt
            fix_ok = await repo.record_fix_attempt(
                incident_id=inc_id,
                suggestion_id="SUG-101",
                action="kill idle transactions",
                outcome="worked",
                note="Cleared locked row",
            )
            assert fix_ok is True

            # 3. Resolve incident
            resolved_ok = await repo.resolve_incident(
                incident_id=inc_id,
                root_cause="Concurrent update conflict during checkout",
                fix="Applied select for update with skip locked",
                duration_min=12,
            )
            assert resolved_ok is True

            updated = await repo.get_incident(inc_id)
            assert updated["status"] == "resolved"
            assert updated["duration_min"] == 12
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_record_agent_suggestion(async_repo):
    async def _test():
        engine, session, repo = await async_repo()
        try:
            await repo.seed_demo_data()

            suggestion_data = {
                "hypothesis": "Connection pool full post deploy",
                "confidence": 0.92,
                "cited_incident_ids": ["INC-1987"],
                "failed_fixes_warning": ["Do NOT restart payments-db"],
                "recommended_action": "Rollback release v2.4.1",
                "likely_owner": "payments-platform-team (@alice-sre)",
                "model_used": "openai/gpt-oss-120b",
            }
            sug_id = await repo.record_agent_suggestion("INC-2045", suggestion_data)
            assert sug_id.startswith("SUG-")
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())
