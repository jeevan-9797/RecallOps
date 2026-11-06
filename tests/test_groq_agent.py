"""
Tests for Groq Agent Foundation and Model Fallback.
Validates multi-turn ReAct loop simulation, response parsing,
and failover from primary to fallback model.
"""

import asyncio
import json
from unittest.mock import MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.db.base import Base
from backend.app.db.repository import SQLAlchemyRepository
from backend.app.schemas.agent_tools import AgentTriageResponse
from backend.app.services.band_adapter import MockBandAdapter
from backend.app.services.groq_agent import GroqAgent
from backend.app.services.hindsight_service import HindsightService
from backend.app.services.tool_handlers import AgentToolDispatcher


@pytest.fixture
def mock_agent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session = session_factory()
        repo = SQLAlchemyRepository(session)
        await repo.seed_demo_data()

        hindsight = HindsightService(api_key=None)
        band = MockBandAdapter()
        dispatcher = AgentToolDispatcher(db_repo=repo, hindsight=hindsight, band=band)
        agent = GroqAgent(tool_dispatcher=dispatcher)
        return engine, session, agent

    return _setup


def test_agent_simulated_triage_memory_on(mock_agent):
    async def _test():
        engine, session, agent = await mock_agent()
        try:
            # Run triage loop with memory enabled
            triage = await agent.run_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="HTTP 500 spike post deploy v2.4.1",
                memory_enabled=True,
            )
            assert isinstance(triage, AgentTriageResponse)
            assert triage.incident_id == "INC-2045"
            assert triage.confidence >= 0.85
            assert "INC-1987" in triage.cited_incident_ids
            assert len(triage.failed_fixes_warning) >= 1
            assert "Do NOT restart payments-db" in triage.failed_fixes_warning[0]
            assert "payments-platform-team" in triage.likely_owner
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_agent_simulated_triage_memory_off(mock_agent):
    async def _test():
        engine, session, agent = await mock_agent()
        try:
            # Run triage loop with memory disabled (naive mode)
            triage = await agent.run_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="HTTP 500 spike post deploy v2.4.1",
                memory_enabled=False,
            )
            assert isinstance(triage, AgentTriageResponse)
            assert triage.incident_id == "INC-2045"
            assert triage.confidence <= 0.60
            assert len(triage.cited_incident_ids) == 0
            assert len(triage.failed_fixes_warning) == 0
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_agent_response_parsing_clean_json(mock_agent):
    async def _test():
        engine, session, agent = await mock_agent()
        try:
            valid_payload = json.dumps({
                "incident_id": "INC-2045",
                "hypothesis": "Unindexed query in checkout-api v2.4.1 causing connection pool deadlock",
                "confidence": 0.95,
                "cited_incident_ids": ["INC-1987"],
                "failed_fixes_warning": ["Do NOT restart payments-db"],
                "recommended_action": "Rollback to release v2.4.0",
                "likely_owner": "payments-platform-team (@alice-sre)",
            })

            # 1. Clean JSON string
            parsed = agent._parse_agent_response(valid_payload, "INC-2045", "checkout-api")
            assert parsed is not None
            assert parsed.confidence == 0.95

            # 2. Markdown fenced code block
            fenced = f"```json\n{valid_payload}\n```"
            parsed_fenced = agent._parse_agent_response(fenced, "INC-2045", "checkout-api")
            assert parsed_fenced is not None
            assert parsed_fenced.confidence == 0.95

            # 3. Conversational preamble around JSON
            preamble = f"Here is my diagnostic analysis:\n{valid_payload}\nHope this helps."
            parsed_preamble = agent._parse_agent_response(preamble, "INC-2045", "checkout-api")
            assert parsed_preamble is not None
            assert parsed_preamble.incident_id == "INC-2045"
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_agent_model_fallback_on_error(mock_agent):
    async def _test():
        engine, session, agent = await mock_agent()
        try:
            # Mock live client that fails on primary model, succeeds on fallback
            mock_client = MagicMock()
            agent._client = mock_client

            def mock_create(model, messages, **kwargs):
                if model == "openai/gpt-oss-120b":
                    raise Exception("RateLimitError: 429 Too Many Requests")
                elif model == "qwen/qwen3-32b":
                    # Return final message on fallback
                    mock_msg = MagicMock()
                    mock_msg.tool_calls = None
                    mock_msg.content = json.dumps({
                        "incident_id": "INC-2045",
                        "hypothesis": "Fallback model diagnosed connection exhaustion",
                        "confidence": 0.88,
                        "cited_incident_ids": ["INC-1987"],
                        "failed_fixes_warning": ["Do NOT restart payments-db"],
                        "recommended_action": "Rollback v2.4.1",
                        "likely_owner": "payments-platform-team",
                    })
                    mock_choice = MagicMock()
                    mock_choice.message = mock_msg
                    mock_resp = MagicMock()
                    mock_resp.choices = [mock_choice]
                    return mock_resp
                raise ValueError("Unexpected model")

            mock_client.chat.completions.create.side_effect = mock_create

            triage = await agent.run_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="Latency spike",
            )
            assert triage is not None
            assert "Fallback model" in triage.hypothesis
            assert triage.confidence == 0.88
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())
