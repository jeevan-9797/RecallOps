"""
Unit and Integration Tests for Server-Derived Engineer Identity and Personal Memory Isolation (Phase P4C-R2).

Strictly verifies the 8 required security scenarios:
1. Caller supplies engineer_id=rahul, service owner is Priya: Rahul's bank is never queried.
2. Caller supplies engineer_id=priya, service owner is Rahul: only Rahul's bank can be queried.
3. Caller omits engineer_id: server-derived owner is used if the service ownership record is valid.
4. Missing service owner: no personal bank query.
5. Unknown service owner: no personal bank query.
6. Memory OFF: neither bank is queried.
7. Organizational memory remains available when personal identity is unavailable.
8. No arbitrary caller-provided engineer ID can select a personal bank.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, call
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.models import Engineer, Service
from backend.app.db.repository import SQLAlchemyRepository
from backend.app.prompts.system_prompts import BASELINE_NAIVE_SRE_PROMPT
from backend.app.schemas.agent_tools import AgentTriageResponse
from backend.app.services.band_adapter import MockBandAdapter
from backend.app.services.groq_agent import GroqAgent
from backend.app.services.hindsight_service import HindsightService
from backend.app.services.tool_handlers import AgentToolDispatcher


@pytest.fixture
def auth_agent_context():
    """Provides an isolated GroqAgent, SQLite DB, and spied HindsightService."""
    async def _setup():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        session = session_factory()
        repo = SQLAlchemyRepository(session)
        await repo.seed_demo_data()

        # Seed data check:
        # Service 1: checkout-api -> Owner 4: Priya Sharma (@priya.sharma, handle: priya)
        # Service 3: orders-worker -> Owner 2: Diya Patel (@diya.patel, handle: diya)

        # Register Rahul as engineer and owner of notification-service
        rahul_eng = Engineer(id=99, name="Rahul Verma", team="Platform Squad", slack_handle="@rahul.verma")
        rahul_svc = Service(id=99, name="notification-service", team="Platform Squad", owner_id=99, tier="Tier-2")
        session.add(rahul_eng)
        session.add(rahul_svc)

        # Register unassigned service with no owner
        unassigned_svc = Service(id=100, name="unassigned-service", team="Platform Squad", owner_id=None, tier="Tier-3")
        session.add(unassigned_svc)
        await session.flush()

        hindsight = HindsightService(api_key=None)
        # Register test preferences in personal banks
        await hindsight.remember_engineer_preference(
            engineer_id="priya",
            preference="Prefers immediate root-cause rollbacks before running deep query profile scripts.",
        )
        await hindsight.remember_engineer_preference(
            engineer_id="diya",
            preference="Prefers async worker queue drain commands before restarting workers.",
        )
        await hindsight.remember_engineer_preference(
            engineer_id="rahul",
            preference="Prefers detailed step-by-step mitigation guides with rollback triggers.",
        )

        band = MockBandAdapter()
        dispatcher = AgentToolDispatcher(db_repo=repo, hindsight=hindsight, band=band)
        agent = GroqAgent(tool_dispatcher=dispatcher, db_repo=repo, hindsight=hindsight)
        agent._client = False  # Ensure unit test exercises deterministic simulated triage
        return engine, session, agent, hindsight, repo

    return _setup


# ==============================================================================
# TEST 1: Caller supplies engineer_id=rahul, service owner is Priya:
# Rahul's bank is NEVER queried. Only Priya's bank is queried.
# ==============================================================================

def test_caller_rahul_on_priya_service_never_queries_rahul(auth_agent_context, caplog):
    """
    Caller requests triage for checkout-api (owned by Priya) with engineer_id='rahul'.
    Under P4C-R2, personal bank selection is strictly derived from PostgreSQL service owner (Priya).
    Rahul's bank must NEVER be queried.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            pref_spy = AsyncMock(wraps=hindsight.recall_engineer_preferences)
            hindsight.recall_engineer_preferences = pref_spy

            with caplog.at_level(logging.WARNING):
                triage = await agent.run_triage_loop(
                    incident_id="INC-2045",
                    service_name="checkout-api",
                    symptom="HTTP 500 spike post deploy",
                    memory_enabled=True,
                    engineer_id="rahul",
                )

            # 1. Rahul's bank was NEVER queried
            queried_engineers = [c.kwargs.get("engineer_id") for c in pref_spy.call_args_list]
            assert "rahul" not in queried_engineers

            # 2. Server-derived owner Priya's bank was queried
            assert "priya" in queried_engineers

            # 3. Security audit warning was logged ignoring caller-supplied engineer_id
            audit_records = [
                r for r in caplog.records
                if "SECURITY AUDIT: Caller-supplied engineer_id 'rahul' ignored" in r.message
            ]
            assert len(audit_records) >= 1
            assert "priya" in audit_records[0].message
            assert "checkout-api" in audit_records[0].message

            # 4. Triage applies Priya's concise kubectl style (not Rahul's stepwise guide)
            assert "kubectl rollout undo" in triage.recommended_action
            assert "1. Immediate mitigation:" not in triage.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# TEST 2: Caller supplies engineer_id=priya, service owner is Rahul:
# Only Rahul's bank can be queried. Priya's bank is NEVER queried.
# ==============================================================================

def test_caller_priya_on_rahul_service_queries_only_rahul(auth_agent_context, caplog):
    """
    Caller requests triage for notification-service (owned by Rahul) with engineer_id='priya'.
    Under P4C-R2, personal bank selection is strictly derived from PostgreSQL service owner (Rahul).
    Priya's bank must NEVER be queried.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            pref_spy = AsyncMock(wraps=hindsight.recall_engineer_preferences)
            hindsight.recall_engineer_preferences = pref_spy

            with caplog.at_level(logging.WARNING):
                triage = await agent.run_triage_loop(
                    incident_id="INC-4001",
                    service_name="notification-service",
                    symptom="Notification delivery latency spike",
                    memory_enabled=True,
                    engineer_id="priya",
                )

            # 1. Priya's bank was NEVER queried
            queried_engineers = [c.kwargs.get("engineer_id") for c in pref_spy.call_args_list]
            assert "priya" not in queried_engineers

            # 2. Server-derived owner Rahul's bank was queried
            assert "rahul" in queried_engineers

            # 3. Security audit warning logged ignoring caller-supplied engineer_id
            audit_records = [
                r for r in caplog.records
                if "SECURITY AUDIT: Caller-supplied engineer_id 'priya' ignored" in r.message
            ]
            assert len(audit_records) >= 1
            assert "rahul" in audit_records[0].message

            # 4. Triage applies Rahul's stepwise mitigation style
            assert "1. Immediate mitigation:" in triage.recommended_action
            assert "2. Database isolation:" in triage.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# TEST 3: Caller omits engineer_id: server-derived owner used when valid
# ==============================================================================

def test_caller_omits_engineer_id_uses_server_derived_owner(auth_agent_context):
    """
    Caller provides engineer_id=None on checkout-api.
    Server-derived owner (Priya) is resolved from PostgreSQL and used.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            pref_spy = AsyncMock(wraps=hindsight.recall_engineer_preferences)
            hindsight.recall_engineer_preferences = pref_spy

            triage = await agent.run_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=True,
                engineer_id=None,
            )

            # Server-derived owner Priya queried
            pref_spy.assert_called_once_with(engineer_id="priya")
            assert "kubectl rollout undo" in triage.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# TEST 4: Missing service owner: no personal bank query
# ==============================================================================

def test_missing_service_owner_queries_no_personal_bank(auth_agent_context, caplog):
    """
    Service exists in PostgreSQL (unassigned-service) but owner_id is NULL.
    Must query ZERO personal banks and fall back to neutral persona.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            pref_spy = AsyncMock(wraps=hindsight.recall_engineer_preferences)
            hindsight.recall_engineer_preferences = pref_spy

            with caplog.at_level(logging.INFO):
                triage = await agent.run_triage_loop(
                    incident_id="INC-5001",
                    service_name="unassigned-service",
                    symptom="Worker connection pool exhaustion",
                    memory_enabled=True,
                    engineer_id="priya",  # Caller tries to pass Priya on unowned service
                )

            # 1. Zero personal bank queries
            pref_spy.assert_not_called()

            # 2. Audit log indicates service has no registered owner
            audit_records = [
                r for r in caplog.records
                if "has no valid registered owner engineer in database. Zero personal memory banks will be queried" in r.message
            ]
            assert len(audit_records) >= 1

            # 3. Standard neutral balanced recommendation returned
            assert triage.recommended_action == "Rollback unassigned-service to previous release and apply connection pooler limits."
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# TEST 5: Unknown service owner: no personal bank query
# ==============================================================================

def test_unknown_service_owner_queries_no_personal_bank(auth_agent_context, caplog):
    """
    Service is unregistered / non-existent in PostgreSQL (ghost-service).
    Must query ZERO personal banks and fall back to neutral persona.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            pref_spy = AsyncMock(wraps=hindsight.recall_engineer_preferences)
            hindsight.recall_engineer_preferences = pref_spy

            with caplog.at_level(logging.INFO):
                triage = await agent.run_triage_loop(
                    incident_id="INC-6001",
                    service_name="ghost-service",
                    symptom="Unknown panic in service runtime",
                    memory_enabled=True,
                    engineer_id="priya",
                )

            # Zero personal bank queries
            pref_spy.assert_not_called()

            # Audit record confirms no valid registered owner
            audit_records = [
                r for r in caplog.records
                if "ghost-service" in r.message and "Zero personal memory banks will be queried" in r.message
            ]
            assert len(audit_records) >= 1

            assert triage.recommended_action == "Rollback ghost-service to previous release and apply connection pooler limits."
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# TEST 6: Memory OFF: neither bank is queried
# ==============================================================================

def test_memory_off_queries_neither_bank(auth_agent_context):
    """
    Memory is turned off.
    Must query zero organizational and zero personal banks regardless of caller parameters.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            pref_spy = AsyncMock(wraps=hindsight.recall_engineer_preferences)
            hindsight.recall_engineer_preferences = pref_spy

            sim_spy = AsyncMock(wraps=hindsight.recall_similar)
            hindsight.recall_similar = sim_spy

            ff_spy = AsyncMock(wraps=hindsight.recall_failed_fixes)
            hindsight.recall_failed_fixes = ff_spy

            triage = await agent.run_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=False,
                engineer_id="priya",
            )

            # Neither bank is queried
            pref_spy.assert_not_called()
            sim_spy.assert_not_called()
            ff_spy.assert_not_called()

            # Baseline un-augmented output
            assert triage.cited_incident_ids == []
            assert triage.failed_fixes_warning == []
            assert "Restart checkout-api pods" in triage.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# TEST 7: Organizational memory remains available when personal identity is unavailable
# ==============================================================================

def test_organizational_memory_available_when_personal_identity_unavailable(auth_agent_context):
    """
    Service has no owner (unassigned-service), so personal bank is unavailable.
    Organizational memory (kartly-sre precedents and negative-memory failed fixes)
    must STILL be fully recalled and populated in the triage response.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            triage = await agent.run_triage_loop(
                incident_id="INC-2045",
                service_name="unassigned-service",
                symptom="Database connection pool exhaustion",
                memory_enabled=True,
                engineer_id=None,
            )

            # Precedent INC-1987 must still be cited from kartly-sre
            assert "INC-1987" in triage.cited_incident_ids

            # Negative memory warning against restarting payments-db must still be present
            assert len(triage.failed_fixes_warning) >= 1
            assert "Do NOT restart payments-db" in triage.failed_fixes_warning[0]
            assert triage.confidence >= 0.90
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# TEST 8: No arbitrary caller-provided engineer ID can select a personal bank
# ==============================================================================

def test_no_arbitrary_caller_id_can_select_personal_bank(auth_agent_context, caplog):
    """
    Caller provides arbitrary engineer_id='evil_attacker_bank_99' on checkout-api.
    The arbitrary bank must NEVER be queried; only the server-derived owner (priya) is queried.
    """
    async def _test():
        engine, session, agent, hindsight, repo = await auth_agent_context()
        try:
            pref_spy = AsyncMock(wraps=hindsight.recall_engineer_preferences)
            hindsight.recall_engineer_preferences = pref_spy

            with caplog.at_level(logging.WARNING):
                triage = await agent.run_triage_loop(
                    incident_id="INC-2045",
                    service_name="checkout-api",
                    symptom="HTTP 500 spike post deploy",
                    memory_enabled=True,
                    engineer_id="evil_attacker_bank_99",
                )

            # 1. Arbitrary attacker bank was NEVER queried
            queried_engineers = [c.kwargs.get("engineer_id") for c in pref_spy.call_args_list]
            assert "evil_attacker_bank_99" not in queried_engineers

            # 2. Server-derived owner Priya's bank was queried
            assert "priya" in queried_engineers

            # 3. Security audit warning was logged
            audit_records = [
                r for r in caplog.records
                if "SECURITY AUDIT: Caller-supplied engineer_id 'evil_attacker_bank_99' ignored" in r.message
            ]
            assert len(audit_records) >= 1
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())
