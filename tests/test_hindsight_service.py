"""
Tests for Hindsight Service Wrapper.
Validates episodic retention, negative memory retention, recall normalization,
and reflection with both mocked SDK clients and unconfigured fallback mode.
"""

import asyncio
from unittest.mock import MagicMock
import pytest

from backend.app.services.hindsight_service import HindsightService


def test_offline_fallback_recall_and_reflect():
    async def _test():
        # Service initialized without API key (offline mode)
        svc = HindsightService(api_key=None)

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

        # 4. Offline retention returns True
        retained = await svc.remember_incident(
            incident_id="INC-3001",
            service_name="checkout-api",
            symptom="500 spike",
            root_cause="Bad config",
            fix="Rollback",
            duration_min=10,
        )
        assert retained is True

    asyncio.run(_test())


def test_mocked_hindsight_sdk_calls():
    async def _test():
        svc = HindsightService(api_key="hs_live_mock_key_12345", bank_id="kartly-sre")

        # Mock the SDK client
        mock_client = MagicMock()
        svc._client = mock_client

        # Setup mock return for recall
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
        mock_client.recall.return_value = mock_recall_resp

        # Call recall_similar
        results = await svc.recall_similar("payments-db", "connection slots exhausted")
        assert len(results) == 1
        assert results[0]["incident_id"] == "INC-1987"
        assert results[0]["similarity"] == 0.95
        assert results[0]["successful_fix"] == "Applied index and pooler"

        # Verify SDK recall was called with bank_id and tags
        mock_client.recall.assert_called_once_with(
            bank_id="kartly-sre",
            query="service: payments-db symptom: connection slots exhausted",
            tags=["episodic_resolution"],
        )

        # Test retain call
        retain_ok = await svc.remember_fix_outcome(
            incident_id="INC-2045",
            service_name="payments-db",
            signature="ConnectionPoolExhausted",
            attempted_action="systemctl restart postgresql",
            outcome="failed",
            failure_mode="Cold cache crash",
        )
        assert retain_ok is True
        assert mock_client.retain.called

    asyncio.run(_test())
