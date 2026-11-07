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
        agent._client = False  # Ensure unit test exercises deterministic simulated triage
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
            assert ("priya" in triage.likely_owner.lower() or "payment" in triage.likely_owner.lower())
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
                elif model == agent.fallback_model or "qwen" in model:
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


def test_extract_failed_generation_recovery(mock_agent):
    async def _test():
        engine, session, agent = await mock_agent()
        try:
            # Simulate Groq 400 BadRequestError with failed_generation
            class MockBadRequestError(Exception):
                def __init__(self, body):
                    self.body = body

            payload = {
                "error": {
                    "message": "Tool call validation failed: attempted to call tool 'agent_output' which was not in request.tools",
                    "code": "tool_use_failed",
                    "failed_generation": json.dumps({
                        "name": "agent_output",
                        "arguments": {
                            "incident_id": "INC-2045",
                            "hypothesis": "Connection pool exhaustion observed in checkout-api matching [INC-1987]",
                            "confidence": 0.92,
                            "cited_incident_ids": ["INC-1987"],
                            "failed_fixes_warning": ["Do NOT restart payments-db"],
                            "recommended_action": "kubectl rollout restart deployment/checkout-api",
                            "likely_owner": "Priya Sharma (@priya.sharma)",
                        }
                    })
                }
            }
            err = MockBadRequestError(payload)
            res = agent._extract_failed_generation(err, "INC-2045", "checkout-api")
            assert res is not None
            assert isinstance(res, AgentTriageResponse)
            assert res.incident_id == "INC-2045"
            assert res.confidence == 0.92
            assert "INC-1987" in res.cited_incident_ids
            assert "Do NOT restart" in res.failed_fixes_warning[0]
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_agent_react_loop_recovers_from_groq_tool_use_failed(mock_agent):
    async def _test():
        engine, session, agent = await mock_agent()
        try:
            mock_client = MagicMock()
            agent._client = mock_client

            call_count = 0

            class MockBadRequestError(Exception):
                def __init__(self, body):
                    self.body = body

            def mock_create(model, messages, tools=None, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # Model invokes recall_similar_incidents
                    mock_tc = MagicMock()
                    mock_tc.id = "call_123"
                    mock_tc.function.name = "recall_similar_incidents"
                    mock_tc.function.arguments = json.dumps({"service_name": "checkout-api", "symptom": "Latency spike"})
                    mock_msg = MagicMock()
                    mock_msg.tool_calls = [mock_tc]
                    mock_msg.content = "Checking similar incidents..."
                    mock_resp = MagicMock()
                    mock_resp.choices = [MagicMock(message=mock_msg)]
                    return mock_resp
                elif call_count == 2:
                    # Model attempts to output final diagnosis as agent_output tool call
                    payload = {
                        "error": {
                            "message": "Tool call validation failed: attempted to call tool 'agent_output' which was not in request.tools",
                            "code": "tool_use_failed",
                            "failed_generation": json.dumps({
                                "name": "agent_output",
                                "arguments": {
                                    "incident_id": "INC-2045",
                                    "hypothesis": "Connection pool exhaustion verified with [INC-1987]",
                                    "confidence": 0.94,
                                    "cited_incident_ids": ["INC-1987"],
                                    "failed_fixes_warning": ["Do NOT restart payments-db"],
                                    "recommended_action": "kubectl patch configmap checkout-api-config -p '{\"data\":{\"MAX_DB_CONNECTIONS\":\"400\"}}'",
                                    "likely_owner": "Priya Sharma (@priya.sharma)",
                                }
                            })
                        }
                    }
                    raise MockBadRequestError(payload)

            mock_client.chat.completions.create.side_effect = mock_create

            events = []
            async for evt_type, evt_data in agent.stream_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="Latency spike",
                memory_enabled=True,
            ):
                events.append((evt_type, evt_data))

            event_types = [e[0] for e in events]
            assert "thought" in event_types
            assert "tool_call" in event_types
            assert "tool_result" in event_types
            assert "suggestion" in event_types
            assert "done" in event_types

            # Verify suggestion payload
            suggestion_evt = next(e[1] for e in events if e[0] == "suggestion")
            assert suggestion_evt["confidence"] == 0.94
            assert "INC-1987" in suggestion_evt["cited_incident_ids"]
            assert any("Do NOT restart" in w for w in suggestion_evt["failed_fixes_warning"])

            # Verify done event indicates primary model, not safe_fallback
            done_evt = next(e[1] for e in events if e[0] == "done")
            assert done_evt["model_used"] == agent.primary_model
            assert done_evt["status"] == "completed"
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())


def test_agent_react_loop_normalizes_camelcase_tools(mock_agent):
    async def _test():
        engine, session, agent = await mock_agent()
        try:
            mock_client = MagicMock()
            agent._client = mock_client

            call_count = 0

            def mock_create(model, messages, tools=None, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # Model invokes camelCase recallSimilarIncidents
                    mock_tc = MagicMock()
                    mock_tc.id = "call_camel_1"
                    mock_tc.function.name = "recallSimilarIncidents"
                    mock_tc.function.arguments = json.dumps({"service_name": "checkout-api", "symptom": "Latency spike"})
                    mock_msg = MagicMock()
                    mock_msg.tool_calls = [mock_tc]
                    mock_msg.content = "Querying memory..."
                    mock_resp = MagicMock()
                    mock_resp.choices = [MagicMock(message=mock_msg)]
                    return mock_resp
                elif call_count == 2:
                    # Model returns conclusion as normal JSON
                    mock_msg = MagicMock()
                    mock_msg.tool_calls = None
                    mock_msg.content = json.dumps({
                        "incident_id": "INC-2045",
                        "hypothesis": "Resolved via precedent [INC-1987]",
                        "confidence": 0.91,
                        "cited_incident_ids": ["INC-1987"],
                        "failed_fixes_warning": [],
                        "recommended_action": "Apply connection pool patch",
                        "likely_owner": "Priya Sharma",
                    })
                    mock_resp = MagicMock()
                    mock_resp.choices = [MagicMock(message=mock_msg)]
                    return mock_resp

            mock_client.chat.completions.create.side_effect = mock_create

            events = []
            async for evt_type, evt_data in agent.stream_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="Latency spike",
                memory_enabled=True,
            ):
                events.append((evt_type, evt_data))

            # Verify tool_call was normalized to recall_similar_incidents
            tool_calls = [e[1] for e in events if e[0] == "tool_call"]
            assert len(tool_calls) == 1
            assert tool_calls[0]["tool"] == "recall_similar_incidents"
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_test())
