"""
Unit and Integration Tests for Dynamic System Prompt Integration (Phase P4C).
Validates:
1. Priya receives concise command-oriented style.
2. Rahul receives detailed step-by-step style.
3. Engineer A cannot receive Engineer B's preferences.
4. Missing engineer_id uses safe default style.
5. Unknown engineer_id never falls back to another bank.
6. Memory OFF bypasses both banks and uses BASELINE_NAIVE_SRE_PROMPT.
7. Memory ON preserves organizational and personal isolation.
8. Failed-fix warnings remain present.
9. Existing tool calls and output schema remain unchanged.
10. SSE event sequence remains compatible.
"""

import asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.repository import SQLAlchemyRepository
from backend.app.prompts.system_prompts import (
    BASELINE_NAIVE_SRE_PROMPT,
    PRODUCTION_RECALLOPS_SRE_PROMPT,
    SENIOR_SRE_SYSTEM_PROMPT,
    build_sre_system_prompt,
)
from backend.app.schemas.agent_tools import AgentTriageResponse
from backend.app.services.band_adapter import MockBandAdapter
from backend.app.services.groq_agent import GroqAgent
from backend.app.services.hindsight_service import HindsightService
from backend.app.services.tool_handlers import AgentToolDispatcher


@pytest.fixture
def mock_agent_context():
    """Provides an isolated GroqAgent and in-memory test database."""
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

        hindsight = HindsightService(api_key=None)
        band = MockBandAdapter()
        dispatcher = AgentToolDispatcher(db_repo=repo, hindsight=hindsight, band=band)
        agent = GroqAgent(tool_dispatcher=dispatcher, db_repo=repo, hindsight=hindsight)
        agent._client = False  # Ensure unit test exercises deterministic simulated triage
        return engine, session, agent, hindsight

    return _setup


# ==============================================================================
# 1. PERSONA STYLE TESTS (PRIYA VS RAHUL)
# ==============================================================================

def test_priya_concise_command_oriented_style(mock_agent_context):
    """Priya receives concise, copy-ready kubectl commands."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            # 1. Prompt builder verification
            unified = await hindsight.retrieve_unified_memory(
                service_name="checkout-api",
                symptom="Connection pool exhaustion",
                engineer_id="priya",
            )
            prompt = agent.build_system_prompt(
                memory_enabled=True,
                engineer_id="priya",
                unified_memory=unified,
            )
            assert "Assigned Engineer: priya" in prompt
            assert "Prefers immediate root-cause rollbacks" in prompt or "rollback" in prompt.lower()
            assert "Strictly enforce the above preference in `recommended_action`" in prompt

            # 2. Simulated triage output verification
            triage = await agent.run_triage_loop(
                incident_id="INC-2041",
                service_name="checkout-api",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=True,
                engineer_id="priya",
            )
            assert isinstance(triage, AgentTriageResponse)
            assert "kubectl rollout undo" in triage.recommended_action
            assert "kubectl scale" in triage.recommended_action
            # Terse check: should not be multi-paragraph architectural narrative
            assert "1. Immediate mitigation:" not in triage.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_rahul_detailed_stepwise_style(mock_agent_context):
    """Rahul receives structured, stepwise mitigation guides with rollback triggers on services he owns."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            # Register Rahul as engineer and owner of notification-service
            from backend.app.db.models import Engineer, Service
            rahul_eng = Engineer(id=99, name="Rahul Verma", team="Platform Squad", slack_handle="@rahul.verma")
            rahul_svc = Service(id=99, name="notification-service", team="Platform Squad", owner_id=99, tier="Tier-2")
            session.add(rahul_eng)
            session.add(rahul_svc)
            await session.flush()

            # Retain preference in Rahul's personal bank
            await hindsight.remember_engineer_preference(
                engineer_id="rahul",
                preference="Prefers detailed step-by-step mitigation guides with rollback triggers and deep observability verification.",
            )

            # 1. Prompt builder verification
            unified = await hindsight.retrieve_unified_memory(
                service_name="notification-service",
                symptom="Connection pool exhaustion",
                engineer_id="rahul",
            )
            prompt = agent.build_system_prompt(
                memory_enabled=True,
                engineer_id="rahul",
                unified_memory=unified,
            )
            assert "Assigned Engineer: rahul" in prompt
            assert "Prefers detailed step-by-step" in prompt or "step-by-step" in prompt.lower()

            # 2. Simulated triage output verification on service owned by Rahul
            triage = await agent.run_triage_loop(
                incident_id="INC-2041",
                service_name="notification-service",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=True,
                engineer_id="rahul",
            )
            assert isinstance(triage, AgentTriageResponse)
            assert "1. Immediate mitigation:" in triage.recommended_action
            assert "2. Database isolation:" in triage.recommended_action
            assert "3. Verification:" in triage.recommended_action
            assert "4. Rollback trigger:" in triage.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# 2. ISOLATION & LEAK PREVENTION TESTS
# ==============================================================================

def test_engineer_a_cannot_receive_engineer_b_preferences(mock_agent_context):
    """Strict isolation: Priya cannot receive Rahul's preferences, and vice versa."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            priya_unified = await hindsight.retrieve_unified_memory(
                service_name="checkout-api",
                symptom="Connection pool exhaustion",
                engineer_id="priya",
            )
            rahul_unified = await hindsight.retrieve_unified_memory(
                service_name="checkout-api",
                symptom="Connection pool exhaustion",
                engineer_id="rahul",
            )

            priya_prompt = agent.build_system_prompt(
                memory_enabled=True,
                engineer_id="priya",
                unified_memory=priya_unified,
            )
            rahul_prompt = agent.build_system_prompt(
                memory_enabled=True,
                engineer_id="rahul",
                unified_memory=rahul_unified,
            )

            # Priya prompt must NOT contain Rahul or Rahul's specific phrases
            assert "rahul" not in priya_prompt.lower().split("### active on-call engineer context")[1]
            assert "step-by-step verification" not in priya_prompt.lower()

            # Rahul prompt must NOT contain Priya
            assert "priya" not in rahul_prompt.lower().split("### active on-call engineer context")[1]
            assert "immediate root-cause rollbacks before running deep" not in rahul_prompt.lower()
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_missing_engineer_id_uses_safe_default_style(mock_agent_context):
    """Missing engineer_id (None) on unassigned service uses safe default balanced style without crashing."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            from backend.app.db.models import Service
            session.add(Service(id=101, name="unassigned-service", team="Platform Squad", owner_id=None, tier="Tier-3"))
            await session.flush()

            unified = await hindsight.retrieve_unified_memory(
                service_name="unassigned-service",
                symptom="Connection pool exhaustion",
                engineer_id=None,
            )
            assert unified["engineer_preferences"] == []

            prompt = agent.build_system_prompt(
                memory_enabled=True,
                engineer_id=None,
                unified_memory=unified,
            )
            # No engineer context section added when engineer_id and preferences are both None
            assert "ACTIVE ON-CALL ENGINEER CONTEXT" not in prompt

            triage = await agent.run_triage_loop(
                incident_id="INC-2041",
                service_name="unassigned-service",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=True,
                engineer_id=None,
            )
            # Default balanced recommendation
            assert triage.recommended_action == "Rollback unassigned-service to previous release and apply connection pooler limits."
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_unknown_engineer_id_never_falls_back_to_another_bank(mock_agent_context):
    """An unknown engineer ID on an unassigned service returns empty preferences and defaults safely."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            from backend.app.db.models import Service
            session.add(Service(id=102, name="unassigned-service-2", team="Platform Squad", owner_id=None, tier="Tier-3"))
            await session.flush()

            unified = await hindsight.retrieve_unified_memory(
                service_name="unassigned-service-2",
                symptom="Connection pool exhaustion",
                engineer_id="unknown_dev_42",
            )
            assert unified["engineer_preferences"] == []

            prompt = agent.build_system_prompt(
                memory_enabled=True,
                engineer_id="unknown_dev_42",
                unified_memory=unified,
            )
            assert "Assigned Engineer: unknown_dev_42" in prompt
            assert "Standard SRE diagnostic style (balanced)." in prompt
            # Must not contain Priya or Rahul's preferences
            assert "root-cause rollbacks before running deep" not in prompt
            assert "step-by-step verification commands" not in prompt

            triage = await agent.run_triage_loop(
                incident_id="INC-2041",
                service_name="unassigned-service-2",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=True,
                engineer_id="unknown_dev_42",
            )
            assert triage.recommended_action == "Rollback unassigned-service-2 to previous release and apply connection pooler limits."
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# 3. MEMORY ON / OFF & REASONING BOUNDS
# ==============================================================================

def test_memory_off_bypasses_both_banks(mock_agent_context):
    """Memory OFF strictly uses BASELINE_NAIVE_SRE_PROMPT with no personal context."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            prompt = agent.build_system_prompt(
                memory_enabled=False,
                engineer_id="priya",
                unified_memory={"engineer_preferences": [{"text": "Priya preference"}]},
            )
            assert prompt == BASELINE_NAIVE_SRE_PROMPT
            assert "priya" not in prompt.lower()
            assert "kartly-sre" not in prompt
            assert "INC-1987" not in prompt

            triage = await agent.run_triage_loop(
                incident_id="INC-2041",
                service_name="checkout-api",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=False,
                engineer_id="priya",
            )
            assert triage.cited_incident_ids == []
            assert triage.failed_fixes_warning == []
            assert "Restart checkout-api pods" in triage.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_memory_on_preserves_bank_isolation(mock_agent_context):
    """Memory ON accurately partitions organizational memories from personal preferences."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            unified = await hindsight.retrieve_unified_memory(
                service_name="checkout-api",
                symptom="Connection pool exhaustion",
                engineer_id="priya",
            )
            for hit in unified["memory_hits"]:
                if hit["bank_type"] == "organizational":
                    assert hit["bank_id"] == "kartly-sre"
                elif hit["bank_type"] == "engineer":
                    assert hit["bank_id"] == "engineer-priya"

            prompt = agent.build_system_prompt(
                memory_enabled=True,
                engineer_id="priya",
                unified_memory=unified,
            )
            assert "kartly-sre" in prompt
            assert "engineer-priya" in prompt or "priya" in prompt
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_failed_fix_warnings_remain_present(mock_agent_context):
    """Failed fix warnings from negative memory remain present and enforced."""
    async def _test():
        engine, session, agent, hindsight = await mock_agent_context()
        try:
            triage = await agent.run_triage_loop(
                incident_id="INC-2041",
                service_name="checkout-api",
                symptom="Database connection pool exhaustion",
                memory_enabled=True,
                engineer_id="priya",
            )
            assert len(triage.failed_fixes_warning) >= 1
            assert "Do NOT restart payments-db" in triage.failed_fixes_warning[0]
            assert "restart payments-db" not in triage.recommended_action.lower()
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# 4. SSE PROTOCOL & EVENT SEQUENCE TESTS
# ==============================================================================

def test_sse_event_sequence_remains_compatible(mock_agent_context):
    """SSE event emission order conforms to the protocol (thought, tools, suggestion, done)."""
    async def _test():
        engine, session, agent, _ = await mock_agent_context()
        try:
            events = []
            async for ev_type, ev_data in agent.stream_triage_loop(
                incident_id="INC-2041",
                service_name="checkout-api",
                symptom="HTTP 500 spike post deploy",
                memory_enabled=True,
                engineer_id="priya",
            ):
                events.append((ev_type, ev_data))

            event_types = [e[0] for e in events]
            assert "thought" in event_types
            assert "tool_call" in event_types
            assert "tool_result" in event_types
            assert "memory_hit" in event_types
            assert "warning" in event_types
            assert "suggestion" in event_types
            assert "done" in event_types

            # Verify suggestion payload strictly conforms to AgentTriageResponse
            suggestion_data = next(e[1] for e in events if e[0] == "suggestion")
            parsed = AgentTriageResponse.model_validate(suggestion_data)
            assert parsed.incident_id == "INC-2041"
            assert "kubectl rollout undo" in parsed.recommended_action
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())
