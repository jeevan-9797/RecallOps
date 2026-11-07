"""
Unit and Integration Tests for Hindsight Cloud Async Service Wrapper.
Validates:
1. Native async SDK operations (aretain, arecall, areflect, aget_bank_config, aget_version).
2. Safe cloud liveness check (aget_version probe, auth/network/server error classification).
3. Graceful offline fallback and no-false-success on live retain failure.
4. Memory OFF isolation (zero Hindsight calls).
5. Personal bank strict isolation and non-substitution invariants.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from hindsight_client_api.exceptions import ApiException

from backend.app.config import settings
from backend.app.services.hindsight_service import (
    HindsightService,
    _scrub_credentials,
    sanitize_engineer_id,
)


# ==============================================================================
# 1. Offline Mode Tests
# ==============================================================================


@pytest.mark.anyio
async def test_offline_fallback_recall_and_reflect():
    """Service initialized without API key operates fully in verified offline mode."""
    svc = HindsightService(api_key="")

    # 1. Recall similar incidents (Kartly checkout)
    similar = await svc.recall_similar("checkout-api", "connection slots exhausted")
    assert len(similar) >= 1
    assert similar[0]["incident_id"] == "INC-1987"
    assert similar[0]["memory_type"] == "episodic_resolution"
    assert "PgBouncer" in similar[0]["successful_fix"]

    # 2. Recall failed fixes (negative memory)
    failed = await svc.recall_failed_fixes("payments-db", "connection exhaustion")
    assert len(failed) >= 1
    assert failed[0]["failed_fix_id"] == "FF-302"
    assert "Do NOT restart payments-db" in failed[0]["warning_directive"]

    # 3. Learned patterns (reflect)
    patterns = await svc.learned_patterns()
    assert len(patterns) >= 1
    assert any("checkout latency" in p for p in patterns)

    # 4. Offline retention records in memory
    retained = await svc.remember_incident(
        incident_id="INC-3001",
        service_name="checkout-api",
        symptom="500 spike",
        root_cause="Bad config",
        fix="Rollback",
        duration_min=10,
    )
    assert retained is True


# ==============================================================================
# 2. Native Async SDK Operations Tests (Mocks)
# ==============================================================================


@pytest.mark.anyio
async def test_async_sdk_recall_and_retain():
    """Validates arecall and aretain are invoked asynchronously with proper parameters."""
    svc = HindsightService(api_key="hs_live_mock_key_12345", bank_id="kartly-sre", enabled=True)

    mock_client = MagicMock()
    svc._client = mock_client

    # Setup mock return for arecall
    mock_result = MagicMock()
    mock_result.id = "INC-1987"
    mock_result.text = "Connection pool leak"
    mock_result.metadata = {
        "incident_id": "INC-1987",
        "memory_type": "episodic_resolution",
        "service_name": "payments-db",
        "symptom": "Connection slots exhausted",
        "root_cause": "Unindexed query",
        "successful_fix": "Applied index and pooler",
        "duration_min": 18,
        "timestamp": "2026-09-14T10:15:00Z",
    }
    mock_result.scores = {"similarity": 0.95}

    mock_recall_resp = MagicMock()
    mock_recall_resp.results = [mock_result]
    mock_client.arecall = AsyncMock(return_value=mock_recall_resp)
    mock_client.aretain = AsyncMock(return_value=MagicMock(success=True))

    # 1. Test async recall_similar
    results = await svc.recall_similar("payments-db", "connection slots exhausted")
    assert len(results) == 1
    assert results[0]["incident_id"] == "INC-1987"
    assert results[0]["similarity"] == 0.95
    mock_client.arecall.assert_awaited_once_with(
        bank_id="kartly-sre",
        query="service: payments-db symptom: connection slots exhausted",
        tags=["episodic_resolution"],
    )

    # 2. Test async remember_fix_outcome (negative memory)
    retain_ok = await svc.remember_fix_outcome(
        incident_id="INC-2045",
        service_name="payments-db",
        signature="ConnectionPoolExhausted",
        attempted_action="systemctl restart postgresql",
        outcome="failed",
        failure_mode="Cold cache crash",
    )
    assert retain_ok is True
    assert mock_client.aretain.await_count == 1
    args, kwargs = mock_client.aretain.call_args
    assert kwargs["bank_id"] == "kartly-sre"
    assert kwargs["context"] == "failed_fix"
    assert "failed_fix" in kwargs["tags"]


@pytest.mark.anyio
async def test_async_sdk_reflect():
    """Validates areflect is invoked asynchronously."""
    svc = HindsightService(api_key="hs_live_mock_key_12345", bank_id="kartly-sre", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    mock_client.areflect = AsyncMock(
        return_value=MagicMock(text="1. Frequent pool leaks\n2. Unindexed joins")
    )

    patterns = await svc.learned_patterns("test query")
    assert len(patterns) == 2
    assert "Frequent pool leaks" in patterns[0]
    mock_client.areflect.assert_awaited_once_with(
        bank_id="kartly-sre",
        query="test query",
    )


@pytest.mark.anyio
async def test_async_bank_exists():
    """Validates async bank existence checks via aget_bank_config."""
    svc = HindsightService(api_key="hs_live_mock_key_12345", bank_id="kartly-sre", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    # Bank exists
    mock_client.aget_bank_config = AsyncMock(return_value={"bank_id": "kartly-sre"})
    assert await svc.bank_exists("kartly-sre") is True

    # Bank missing
    mock_client.aget_bank_config = AsyncMock(side_effect=Exception("Bank not found"))
    assert await svc.bank_exists("engineer-nonexistent") is False


# ==============================================================================
# 3. Safe Cloud Liveness Probe Tests
# ==============================================================================


@pytest.mark.anyio
async def test_check_cloud_liveness_success():
    """Liveness probe succeeds using aget_version without modifying memory."""
    svc = HindsightService(api_key="hs_live_mock_key_12345", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    mock_client.aget_version = AsyncMock(return_value=MagicMock(version="1.2.0"))

    result = await svc.check_cloud_liveness()
    assert result["status"] == "connected"
    assert result["reachable"] is True
    assert result["authenticated"] is True
    assert result["version"] == "1.2.0"
    assert result["error"] is None
    mock_client.aget_version.assert_awaited_once()


@pytest.mark.anyio
async def test_check_cloud_liveness_unauthenticated():
    """Distinguishes 401/403 authentication failures."""
    svc = HindsightService(api_key="hs_invalid_key", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    mock_client.aget_version = AsyncMock(side_effect=ApiException(status=401, reason="Unauthorized"))

    result = await svc.check_cloud_liveness()
    assert result["status"] == "unauthenticated"
    assert result["reachable"] is True
    assert result["authenticated"] is False
    assert "invalid or expired" in result["error"]
    assert "hs_invalid_key" not in result["error"]


@pytest.mark.anyio
async def test_check_cloud_liveness_network_failure():
    """Distinguishes endpoint connection/network unreachable errors."""
    svc = HindsightService(api_key="hs_live_key", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    mock_client.aget_version = AsyncMock(side_effect=Exception("Cannot connect to host api.hindsight.vectorize.io:443"))

    result = await svc.check_cloud_liveness()
    assert result["status"] == "unreachable"
    assert result["reachable"] is False
    assert result["authenticated"] is False
    assert "unreachable" in result["error"]


@pytest.mark.anyio
async def test_check_cloud_liveness_server_error():
    """Distinguishes 5xx server errors."""
    svc = HindsightService(api_key="hs_live_key", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    mock_client.aget_version = AsyncMock(side_effect=ApiException(status=503, reason="Service Unavailable"))

    result = await svc.check_cloud_liveness()
    assert result["status"] == "server_error"
    assert result["reachable"] is True
    assert "HTTP 503" in result["error"]


@pytest.mark.anyio
async def test_check_cloud_liveness_offline_mode():
    """When no API key is provided, liveness probe reports offline mode."""
    svc = HindsightService(api_key="")
    result = await svc.check_cloud_liveness()
    assert result["status"] == "offline_mode"
    assert result["mode"] == "offline_mock"
    assert result["reachable"] is False


# ==============================================================================
# 4. Error Handling & No False Success Tests
# ==============================================================================


@pytest.mark.anyio
async def test_no_false_success_when_live_retain_fails():
    """When live cloud retain raises an error, the method must return False, not claim success."""
    svc = HindsightService(api_key="hs_live_key", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    mock_client.aretain = AsyncMock(side_effect=Exception("Failed to persist in bank"))

    ok1 = await svc.remember_incident("INC-1", "checkout", "symptom", "root", "fix", 10)
    assert ok1 is False

    ok2 = await svc.remember_fix_outcome("INC-1", "checkout", "sym", "action", "failed")
    assert ok2 is False

    ok3 = await svc.remember_engineer_preference("priya", "prefers concise diffs")
    assert ok3 is False


@pytest.mark.anyio
async def test_live_recall_failure_returns_empty_without_crashing():
    """Live recall failure returns empty list and does not raise uncaught exception."""
    svc = HindsightService(api_key="hs_live_key", enabled=True)
    mock_client = MagicMock()
    svc._client = mock_client

    mock_client.arecall = AsyncMock(side_effect=Exception("502 Bad Gateway"))

    res1 = await svc.recall_similar("checkout-api", "500 spike")
    assert res1 == []

    res2 = await svc.recall_failed_fixes("checkout-api", "500 spike")
    assert res2 == []


# ==============================================================================
# 5. Personal Bank Isolation & Non-Substitution Invariants
# ==============================================================================


@pytest.mark.anyio
async def test_personal_bank_non_substitution_when_missing():
    """If engineer bank does not exist, never substitute kartly-sre."""
    svc = HindsightService(api_key="hs_live_key", enabled=True)
    mock_client = MagicMock()
    mock_client.arecall = AsyncMock()
    svc._client = mock_client

    # Bank does not exist
    mock_client.aget_bank_config = AsyncMock(side_effect=Exception("Bank not found"))

    prefs = await svc.recall_engineer_preferences("unknown-engineer-999")
    assert prefs == []
    # Verify arecall was NOT called on kartly-sre
    assert mock_client.arecall.await_count == 0


def test_sanitize_engineer_id_strict_validation():
    """Rejects malicious or invalid engineer identifiers."""
    assert sanitize_engineer_id("priya") == "priya"
    assert sanitize_engineer_id("@Priya_99") == "priya_99"
    assert sanitize_engineer_id("engineer-1") == "engineer-1"

    with pytest.raises(ValueError):
        sanitize_engineer_id("../malicious/bank")

    with pytest.raises(ValueError):
        sanitize_engineer_id("engineer;DROP TABLE;")


def test_scrub_credentials_redacts_tokens_and_keys():
    """Verifies credentials are scrubbed from log strings."""
    raw = "Bearer hs_secret_token_1234567890 key='my_secret_key_abcdef' failed"
    scrubbed = _scrub_credentials(raw)
    assert "hs_secret_token_1234567890" not in scrubbed
    assert "my_secret_key_abcdef" not in scrubbed


# ==============================================================================
# 6. Phase 5A: Parked / Disabled Hindsight Cloud Mode Tests
# ==============================================================================


@pytest.mark.anyio
async def test_disabled_mode_prevents_client_initialization_and_network_calls():
    """When HINDSIGHT_ENABLED is False, _get_client returns None even with valid API key."""
    svc = HindsightService(api_key="hs_valid_live_api_key_12345", enabled=False)
    assert svc.enabled is False
    assert svc._get_client() is None

    # Even if an internal _client was assigned, _get_client must return None when disabled
    mock_client = MagicMock()
    svc._client = mock_client
    assert svc._get_client() is None


@pytest.mark.anyio
async def test_disabled_mode_check_cloud_liveness_returns_offline():
    """Liveness probe immediately returns offline mode without any network calls."""
    svc = HindsightService(api_key="hs_valid_live_api_key_12345", enabled=False)
    mock_client = MagicMock()
    mock_client.aget_version = AsyncMock()
    svc._client = mock_client

    res = await svc.check_cloud_liveness()
    assert res["status"] == "offline_mode"
    assert res["mode"] == "offline_mock"
    assert res["reachable"] is False
    assert res["authenticated"] is False
    assert "parked" in res["error"]
    # Zero calls to aget_version
    mock_client.aget_version.assert_not_called()


@pytest.mark.anyio
async def test_disabled_mode_offline_memory_operations():
    """Disabled mode successfully executes all memory operations locally without live network."""
    svc = HindsightService(api_key="hs_valid_live_api_key_12345", enabled=False)

    # 1. Recall similar incidents
    similar = await svc.recall_similar("checkout-api", "500 spike")
    assert len(similar) >= 1
    assert any("INC-" in item.get("incident_id", "") for item in similar)

    # 2. Recall failed fixes
    failed = await svc.recall_failed_fixes("payments-db", "connection slots exhausted")
    assert len(failed) >= 1
    assert "Do NOT restart payments-db" in failed[0]["warning_directive"]

    # 3. Recall engineer preferences
    prefs = await svc.recall_engineer_preferences("priya")
    assert len(prefs) >= 1

    # 4. Remember incident locally
    ok = await svc.remember_incident(
        incident_id="INC-OFFLINE-TEST",
        service_name="checkout-api",
        symptom="Offline test",
        root_cause="Mock test",
        fix="None",
        duration_min=5,
    )
    assert ok is True

    # 5. Learned patterns (reflect)
    patterns = await svc.learned_patterns()
    assert len(patterns) >= 1


@pytest.mark.anyio
async def test_enabling_setting_permits_mocked_live_client():
    """Setting enabled=True restores live client operations."""
    svc = HindsightService(api_key="hs_test_key", enabled=True)
    assert svc.enabled is True

    mock_client = MagicMock()
    mock_client.aget_version = AsyncMock(return_value=MagicMock(version="1.1.0"))
    svc._client = mock_client

    assert svc._get_client() is mock_client
    liveness = await svc.check_cloud_liveness()
    assert liveness["status"] == "connected"
    assert liveness["version"] == "1.1.0"


def test_health_endpoint_reports_offline_mock_when_disabled(client):
    """GET /health and GET /health?probe=true report offline_mock_active when Hindsight is disabled."""
    # Standard health check
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["checks"]["hindsight_memory"] == "offline_mock_active"

    # Health check with live probe query
    probe_resp = client.get("/health?probe=true")
    assert probe_resp.status_code == 200
    probe_data = probe_resp.json()
    assert probe_data["status"] == "healthy"
    assert probe_data["checks"]["hindsight_memory"] == "offline_mock_active"

