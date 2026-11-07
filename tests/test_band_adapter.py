"""
Comprehensive Unit & Reliability Tests for RecallOps Band Integration.
Tests:
- Mock adapter compatibility.
- RealBandAdapter successful delivery & rich markdown formatting.
- Idempotency & deduplication.
- Delivery timeout handling.
- Bounded retries on transient errors.
- Non-retryable 4xx client errors (401, 422).
- Recovery and state transition (HEALTHY -> DEGRADED -> HEALTHY).
- Secret redaction in logs.
- Factory adapter selection (Mock vs Real).
- Triage flow insulation: Band failure never breaks ReAct loop or SSE stream.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.app.config import settings
from backend.app.db.base import Base
from backend.app.db.repository import SQLAlchemyRepository
from backend.app.schemas.agent_tools import AgentTriageResponse
from backend.app.services.band_adapter import (
    BandAdapterInterface,
    IdempotencyCache,
    MockBandAdapter,
    RealBandAdapter,
    get_band_adapter,
)
from backend.app.services.groq_agent import GroqAgent
from backend.app.services.hindsight_service import HindsightService
from backend.app.services.tool_handlers import AgentToolDispatcher
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# ==============================================================================
# 1. Mock Adapter Compatibility
# ==============================================================================

@pytest.mark.anyio
async def test_mock_band_adapter_compatibility():
    adapter = MockBandAdapter(room_prefix="test-war-room")
    assert isinstance(adapter, BandAdapterInterface)

    success = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Investigating database saturation",
        sender="Lead SRE",
        metadata={"confidence": 0.95},
    )
    assert success is True
    assert len(adapter.messages_posted) == 1
    entry = adapter.messages_posted[0]
    assert entry["incident_id"] == "INC-2045"
    assert entry["sender"] == "Lead SRE"
    assert entry["metadata"]["confidence"] == 0.95


# ==============================================================================
# 2. RealBandAdapter Successful Delivery & Formatting
# ==============================================================================

@pytest.mark.anyio
async def test_real_band_adapter_success():
    mock_client = MagicMock()
    mock_client.agent_api_messages.create_agent_chat_message = AsyncMock(return_value={"id": "msg-123"})

    adapter = RealBandAdapter(
        agent_id="test-agent-id",
        api_key="band_a_test_key_12345",
        default_room_id="room-kartly-war-room",
        rest_client=mock_client,
    )

    metadata = {
        "severity": "CRITICAL",
        "confidence": 0.94,
        "hypothesis": "Connection pool exhausted due to unindexed query in release v2.4.1.",
        "cited_incident_ids": ["INC-1987", "INC-1842"],
        "failed_fixes_warning": ["Do NOT restart payments-db: caused cascade outage in Sept"],
        "recommended_action": "Rollback payments-service to release v2.4.0",
        "likely_owner": "payments-team (@alice-sre)",
    }

    success = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Critical connection leak",
        sender="Triage Agent",
        metadata=metadata,
    )

    assert success is True
    assert adapter.status == "HEALTHY"
    assert adapter.consecutive_failures == 0

    # Verify mock client call arguments
    mock_client.agent_api_messages.create_agent_chat_message.assert_called_once()
    call_kwargs = mock_client.agent_api_messages.create_agent_chat_message.call_args.kwargs
    assert call_kwargs["chat_id"] == "room-kartly-war-room"
    req_message = call_kwargs["message"]
    assert "INC-2045" in req_message.content
    assert "NEGATIVE MEMORY WARNINGS" in req_message.content
    assert "INC-1987" in req_message.content
    assert "payments-team" in req_message.content


# ==============================================================================
# 3. Idempotency & Deduplication
# ==============================================================================

@pytest.mark.anyio
async def test_real_band_adapter_idempotency():
    mock_client = MagicMock()
    mock_client.agent_api_messages.create_agent_chat_message = AsyncMock(return_value={"id": "msg-123"})

    adapter = RealBandAdapter(
        agent_id="test-agent-id",
        api_key="band_a_test_key",
        default_room_id="room-123",
        rest_client=mock_client,
    )

    # First call - sends
    res1 = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Same diagnostic message",
        sender="Triage Agent",
        metadata={"suggestion_id": "sug-1"},
    )
    assert res1 is True
    assert mock_client.agent_api_messages.create_agent_chat_message.call_count == 1

    # Second call with identical content & suggestion_id - suppressed
    res2 = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Same diagnostic message",
        sender="Triage Agent",
        metadata={"suggestion_id": "sug-1"},
    )
    assert res2 is True
    # Call count must still be 1 (deduplicated)
    assert mock_client.agent_api_messages.create_agent_chat_message.call_count == 1

    # Third call with distinct content - sends
    res3 = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Distinct new diagnostic message",
        sender="Triage Agent",
        metadata={"suggestion_id": "sug-2"},
    )
    assert res3 is True
    assert mock_client.agent_api_messages.create_agent_chat_message.call_count == 2


# ==============================================================================
# 4. Timeout Handling
# ==============================================================================

@pytest.mark.anyio
async def test_real_band_adapter_timeout():
    mock_client = MagicMock()

    async def slow_call(*args, **kwargs):
        await asyncio.sleep(1.0)
        return {"id": "late"}

    mock_client.agent_api_messages.create_agent_chat_message = AsyncMock(side_effect=slow_call)

    adapter = RealBandAdapter(
        agent_id="test-agent",
        api_key="band_a_test_key",
        default_room_id="room-123",
        delivery_timeout=0.05,  # Short timeout for fast test execution
        max_retries=1,
        rest_client=mock_client,
    )

    success = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Timeout test message",
    )

    assert success is False
    assert adapter.last_error is not None
    assert "timed out" in adapter.last_error.lower()
    assert adapter.consecutive_failures == 1


# ==============================================================================
# 5. Bounded Retries on Transient Errors
# ==============================================================================

@pytest.mark.anyio
async def test_real_band_adapter_transient_retry_success():
    mock_client = MagicMock()
    # Fail on first attempt with 503, succeed on second attempt
    mock_client.agent_api_messages.create_agent_chat_message = AsyncMock(
        side_effect=[Exception("503 Service Unavailable"), {"id": "msg-ok"}]
    )

    adapter = RealBandAdapter(
        agent_id="test-agent",
        api_key="band_a_test_key",
        default_room_id="room-123",
        delivery_timeout=2.0,
        max_retries=2,
        rest_client=mock_client,
    )

    success = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Retry recovery test",
    )

    assert success is True
    assert mock_client.agent_api_messages.create_agent_chat_message.call_count == 2
    assert adapter.status == "HEALTHY"


# ==============================================================================
# 6. Non-retryable 4xx Client Errors & Secret Redaction
# ==============================================================================

class MockHttpError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.anyio
async def test_real_band_adapter_client_error_no_retry_and_secret_redacted():
    mock_client = MagicMock()
    secret_key = "band_a_secret_live_key_98765"
    err = MockHttpError(status_code=401, message=f"Unauthorized: invalid key {secret_key}")
    mock_client.agent_api_messages.create_agent_chat_message = AsyncMock(side_effect=err)

    adapter = RealBandAdapter(
        agent_id="test-agent",
        api_key=secret_key,
        default_room_id="room-123",
        max_retries=2,
        rest_client=mock_client,
    )

    success = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Auth failure test",
    )

    assert success is False
    # Must abort immediately on 401 without retrying
    assert mock_client.agent_api_messages.create_agent_chat_message.call_count == 1
    assert adapter.status == "UNAVAILABLE"
    # Ensure raw secret key is never in last_error
    assert secret_key not in adapter.last_error
    assert "[REDACTED_BAND_KEY]" in adapter.last_error


# ==============================================================================
# 7. Recovery After Degraded State
# ==============================================================================

@pytest.mark.anyio
async def test_real_band_adapter_state_recovery():
    mock_client = MagicMock()
    mock_client.agent_api_messages.create_agent_chat_message = AsyncMock(return_value={"id": "msg-123"})

    adapter = RealBandAdapter(
        agent_id="test-agent",
        api_key="band_a_test_key",
        default_room_id="room-123",
        rest_client=mock_client,
    )

    # Manually simulate degraded state from earlier network outage
    adapter.status = "DEGRADED"
    adapter.consecutive_failures = 3

    success = await adapter.post_incident_update(
        incident_id="INC-2045",
        message="Recovery test message",
    )

    assert success is True
    # Recovers to HEALTHY upon successful delivery
    assert adapter.status == "HEALTHY"
    assert adapter.consecutive_failures == 0


# ==============================================================================
# 8. Factory Selection
# ==============================================================================

def test_get_band_adapter_selection(monkeypatch):
    # Case A: BAND_API_KEY is unset -> MockBandAdapter
    monkeypatch.setattr(settings, "BAND_API_KEY", None)
    adapter = get_band_adapter()
    assert isinstance(adapter, MockBandAdapter)

    # Case B: BAND_API_KEY is placeholder -> MockBandAdapter
    monkeypatch.setattr(settings, "BAND_API_KEY", "your_band_api_key_here")
    adapter = get_band_adapter()
    assert isinstance(adapter, MockBandAdapter)

    # Case C: BAND_API_KEY is valid -> RealBandAdapter
    monkeypatch.setattr(settings, "BAND_API_KEY", "band_a_live_token_abc")
    monkeypatch.setattr(settings, "BAND_DEFAULT_ROOM_ID", "room-live-123")
    adapter = get_band_adapter()
    assert isinstance(adapter, RealBandAdapter)
    assert adapter.default_room_id == "room-live-123"


# ==============================================================================
# 9. Triage Flow Insulation (Band failure never interrupts triage / SSE)
# ==============================================================================

@pytest.mark.anyio
async def test_triage_flow_unaffected_by_band_failure():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = session_factory()
    repo = SQLAlchemyRepository(session)
    await repo.seed_demo_data()

    # Create a deliberately failing RealBandAdapter
    failing_client = MagicMock()
    failing_client.agent_api_messages.create_agent_chat_message = AsyncMock(
        side_effect=Exception("Band platform connection reset")
    )
    failing_band = RealBandAdapter(
        agent_id="test-agent",
        api_key="band_a_test",
        default_room_id="room-123",
        max_retries=0,
        delivery_timeout=0.5,
        rest_client=failing_client,
    )

    hindsight = HindsightService(api_key=None)
    dispatcher = AgentToolDispatcher(db_repo=repo, hindsight=hindsight, band=failing_band)

    # 1. Direct tool call failure handling
    tool_res = await dispatcher.execute_tool(
        "post_to_band_room",
        {"incident_id": "INC-2045", "message": "Alert update", "sender": "Triage Agent"},
    )
    assert tool_res["tool"] == "post_to_band_room"
    assert tool_res["delivered"] is False
    assert tool_res["status"] == "delivery_failed"

    # 2. ReAct triage loop execution
    agent = GroqAgent(tool_dispatcher=dispatcher, db_repo=repo, hindsight=hindsight)
    agent._client = False  # Ensure unit test runs simulated triage deterministically
    events = []
    async for event_type, data in agent.stream_triage_loop(
        incident_id="INC-2045",
        service_name="checkout-api",
        symptom="Connection pool exhausted",
        memory_enabled=True,
    ):
        events.append((event_type, data))

    event_types = [e[0] for e in events]
    assert "suggestion" in event_types
    assert "done" in event_types
    # Verify final suggestion was still produced despite Band failures
    suggestion = next(d for t, d in events if t == "suggestion")
    assert suggestion["incident_id"] == "INC-2045"
    assert suggestion["confidence"] > 0.0

    await session.close()
    await engine.dispose()
