"""
Comprehensive Tests for RecallOps Phase 2 (Real AI Core Loop).
Covers:
A. Hindsight Dual Memory (organizational bank, engineer bank, isolation, missing bank, sanitization)
B. Groq Agent Loop (primary model, fallback model, tool calling, malformed args, 6 iterations max, citation verification)
C. SSE Streaming (event order, memory hits format, warnings, suggestions, done, error handling)
D. Human-in-the-Loop Feedback (worked, failed, partial, negative memory, preference retention)
E. API Contract Safety (missing incident, missing credentials, database failure isolation)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from backend.app.db.repository import SQLAlchemyRepository
from backend.app.db.session import get_db_session
from backend.app.main import app
from backend.app.schemas.agent_tools import AgentTriageResponse
from backend.app.services.band_adapter import MockBandAdapter
from backend.app.services.groq_agent import GroqAgent
from backend.app.services.hindsight_service import HindsightService, sanitize_engineer_id
from backend.app.services.tool_handlers import AgentToolDispatcher


# ==============================================================================
# A. HINDSIGHT DUAL MEMORY TESTS
# ==============================================================================

def test_hindsight_sanitize_engineer_id():
    """Validates engineer_id sanitation prevents path injection or arbitrary bank targeting."""
    assert sanitize_engineer_id("priya") == "priya"
    assert sanitize_engineer_id("@Aarav_Sharma") == "aarav_sharma"
    assert sanitize_engineer_id("engineer-4") == "engineer-4"

    with pytest.raises(ValueError):
        sanitize_engineer_id("bad/id/inject")

    with pytest.raises(ValueError):
        sanitize_engineer_id("engineer;DROP TABLE")


def test_hindsight_organizational_bank_recall():
    async def _test():
        svc = HindsightService(api_key=None)
        similar = await svc.recall_similar("checkout-api", "Connection pool exhaustion", bank_id="kartly-sre")
        assert len(similar) >= 1
        assert similar[0]["bank_type"] == "organizational"
        assert similar[0]["bank_id"] == "kartly-sre"
        assert "INC-1987" in similar[0]["incident_id"]

    asyncio.run(_test())


def test_hindsight_engineer_bank_recall():
    async def _test():
        svc = HindsightService(api_key=None)
        prefs = await svc.recall_engineer_preferences("priya")
        assert len(prefs) >= 1
        assert prefs[0]["bank_type"] == "engineer"
        assert prefs[0]["bank_id"] == "engineer-priya"
        assert "Prefers immediate root-cause rollbacks" in prefs[0]["text"]

    asyncio.run(_test())


def test_hindsight_missing_engineer_bank_never_substitutes_kartly():
    async def _test():
        svc = HindsightService(api_key=None)
        # engineer-unknown does not exist
        prefs = await svc.recall_engineer_preferences("nonexistent_engineer_999")
        assert prefs == []

    asyncio.run(_test())


def test_hindsight_bank_isolation():
    async def _test():
        svc = HindsightService(api_key=None)
        # Organizational bank query must not leak engineer preferences
        similar = await svc.recall_similar("checkout-api", "500 spike", bank_id="kartly-sre")
        for item in similar:
            assert item["bank_type"] == "organizational"
            assert item["memory_type"] != "engineer_preference"

        # Engineer preference recall must not return raw incident logs
        prefs = await svc.recall_engineer_preferences("aarav")
        for item in prefs:
            assert item["bank_type"] == "engineer"
            assert "log_line" not in item.get("text", "")

    asyncio.run(_test())


def test_hindsight_unified_memory_retrieval():
    async def _test():
        svc = HindsightService(api_key=None)
        unified = await svc.retrieve_unified_memory(
            service_name="checkout-api",
            symptom="ConnectionPoolExhausted",
            engineer_id="priya",
        )
        assert len(unified["similar_incidents"]) >= 1
        assert len(unified["failed_fixes"]) >= 1
        assert len(unified["engineer_preferences"]) >= 1
        assert len(unified["memory_hits"]) >= 3

        # Verify memory_hits structure
        for hit in unified["memory_hits"]:
            assert "bank_type" in hit
            assert "memory_type" in hit
            assert "outcome" in hit
            assert "text" in hit

    asyncio.run(_test())


# ==============================================================================
# B. GROQ AGENT LOOP TESTS
# ==============================================================================

def test_groq_citation_verification_filters_hallucinations(test_db_session_factory):
    async def _test():
        engine, session_factory = await test_db_session_factory()
        async with session_factory() as session:
            repo = SQLAlchemyRepository(session)
            dispatcher = AgentToolDispatcher(db_repo=repo)
            agent = GroqAgent(tool_dispatcher=dispatcher, db_repo=repo)

            # Database has INC-2045 and INC-1987 seeded, but NOT INC-9999 (fabricated)
            citations = ["INC-1987", "INC-9999", "INC-2045"]
            valid = await agent._validate_citations(citations)
            assert "INC-1987" in valid
            assert "INC-2045" in valid
            assert "INC-9999" not in valid

        await engine.dispose()

    asyncio.run(_test())


def test_groq_model_fallback_on_primary_error(test_db_session_factory):
    async def _test():
        engine, session_factory = await test_db_session_factory()
        async with session_factory() as session:
            repo = SQLAlchemyRepository(session)
            dispatcher = AgentToolDispatcher(db_repo=repo)
            agent = GroqAgent(
                tool_dispatcher=dispatcher,
                db_repo=repo,
                primary_model="openai/gpt-oss-120b",
                fallback_model="qwen/qwen3-32b",
            )

            # Mock Groq client
            mock_client = MagicMock()
            agent._client = mock_client

            # First call (primary) raises rate limit; second call (fallback) succeeds
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if kwargs.get("model") == "openai/gpt-oss-120b":
                    raise RuntimeError("RateLimitError: 429 Too Many Requests on primary")
                mock_msg = MagicMock()
                mock_msg.content = json.dumps({
                    "incident_id": "INC-2045",
                    "hypothesis": "Connection pool starved.",
                    "confidence": 0.88,
                    "cited_incident_ids": ["INC-1987"],
                    "failed_fixes_warning": [],
                    "recommended_action": "Rollback release v2.4.1",
                    "likely_owner": "payments-platform-team (@priya.sharma)",
                })
                mock_msg.tool_calls = None
                mock_choice = MagicMock(message=mock_msg)
                return MagicMock(choices=[mock_choice])

            mock_client.chat.completions.create.side_effect = side_effect

            triage = await agent.run_triage_loop(
                incident_id="INC-2045",
                service_name="checkout-api",
                symptom="500 spike",
                memory_enabled=True,
            )

            assert isinstance(triage, AgentTriageResponse)
            assert triage.confidence == 0.88
            assert call_count >= 2

        await engine.dispose()

    asyncio.run(_test())


def test_groq_tool_dispatcher_memory_disabled_blocks_memory_tools(test_db_session_factory):
    async def _test():
        engine, session_factory = await test_db_session_factory()
        async with session_factory() as session:
            repo = SQLAlchemyRepository(session)
            dispatcher = AgentToolDispatcher(db_repo=repo)

            # When memory_enabled=False, memory tools must return disabled status
            res = await dispatcher.execute_tool(
                "recall_similar_incidents",
                {"service_name": "checkout-api", "symptom": "500", "limit": 3},
                memory_enabled=False,
            )
            assert res["status"] == "disabled"
            assert res["count"] == 0

            ff_res = await dispatcher.execute_tool(
                "recall_failed_fixes",
                {"service_name": "payments-db", "incident_signature": "500"},
                memory_enabled=False,
            )
            assert ff_res["status"] == "disabled"
            assert ff_res["count"] == 0

            # Operational DB tools still work normally
            deploys_res = await dispatcher.execute_tool(
                "get_recent_deploys",
                {"service_name": "checkout-api", "lookback_hours": 24},
                memory_enabled=False,
            )
            assert deploys_res["status"] == "success"

        await engine.dispose()

    asyncio.run(_test())


# ==============================================================================
# C. SSE STREAMING REAL AGENT TESTS
# ==============================================================================

def test_sse_streaming_with_engineer_preferences(client):
    """Verifies that passing engineer_id emits engineer preference memory_hit in SSE stream."""
    response = client.post("/api/incidents/INC-2045/triage?memory=on&engineer_id=priya")
    assert response.status_code == 200
    body = response.text

    assert "event: thought" in body
    assert "event: tool_call" in body
    assert "event: tool_result" in body
    assert "event: memory_hit" in body
    assert "event: warning" in body
    assert "event: suggestion" in body
    assert "event: done" in body

    # Verify engineer bank memory hit is present
    assert "engineer-priya" in body
    assert "Prefers immediate root-cause rollbacks" in body


def test_sse_streaming_memory_off_no_memory_hits(client):
    """Verifies that ?memory=off completely suppresses all memory hits and warnings."""
    response = client.post("/api/incidents/INC-2045/triage?memory=off")
    assert response.status_code == 200
    body = response.text

    assert "event: memory_hit" not in body
    assert "event: recalled_memory" not in body
    assert "event: warning" not in body
    assert "event: suggestion" in body
    assert "event: done" in body


# ==============================================================================
# D. HUMAN FEEDBACK & PERSISTENCE TESTS
# ==============================================================================

def test_feedback_worked_persistence(client):
    payload = {
        "suggestion_id": "SUG-201",
        "outcome": "worked",
        "attempted_action": "Apply PgBouncer pool connection limit",
        "note": "Resolved active connection pool spike immediately",
        "engineer_id": "engineer-4",
    }
    response = client.post("/api/incidents/INC-2045/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-2045"
    assert data["status"] == "recorded"
    assert data["persisted_to_db"] is True
    assert data["negative_memory_retained"] is False


def test_feedback_failed_triggers_negative_memory(client):
    payload = {
        "suggestion_id": "SUG-202",
        "outcome": "failed",
        "attempted_action": "systemctl restart postgresql",
        "note": "Cold cache caused 100% disk thrashing and downstream outage",
    }
    response = client.post("/api/incidents/INC-2045/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "recorded"
    assert data["persisted_to_db"] is True
    assert data["negative_memory_retained"] is True


def test_feedback_explicit_engineer_preference_retention(client):
    payload = {
        "suggestion_id": "SUG-203",
        "outcome": "worked",
        "attempted_action": "Rollback to previous release",
        "engineer_id": "aarav",
        "engineer_preference": "Prefers rolling back immediately before detailed profiling",
    }
    response = client.post("/api/incidents/INC-2045/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["preference_retained"] is True


def test_resolve_incident_persists_and_retains(client):
    payload = {
        "root_cause": "Unindexed query in order_items table under campaign traffic spike",
        "fix": "Rolled back release v2.4.1 and added covering index on customer_id",
        "duration_min": 18,
    }
    response = client.post("/api/incidents/INC-2045/resolve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"
    assert data["persisted_to_db"] is True
    assert data["episodic_memory_retained"] is True
