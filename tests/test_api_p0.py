"""
Unit and Integration Tests for RecallOps Phase 0 FastAPI Foundation.
Validates all 9 frozen API contracts, SSE streaming, and error handling.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.band_adapter import MockBandAdapter


@pytest.fixture
def client():
    """Provides a synchronous FastAPI TestClient."""
    return TestClient(app)


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["project"] == "RecallOps API"
    assert data["documentation"] == "/docs"
    assert data["health"] == "/health"


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "environment" in data
    assert "checks" in data
    assert "groq_llm" in data["checks"]
    assert "hindsight_memory" in data["checks"]
    assert "postgresql" in data["checks"]


def test_create_alert_success(client):
    payload = {
        "service_name": "checkout-api",
        "symptom": "HTTP 500 spike and latency > 2.5s post release v2.4.1",
        "severity": "CRITICAL",
    }
    response = client.post("/api/alerts", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["incident_id"].startswith("INC-")
    assert data["status"] == "created"
    assert "created_at" in data


def test_create_alert_validation_error(client):
    # Missing required field 'symptom'
    payload = {"service_name": "checkout-api"}
    response = client.post("/api/alerts", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_triage_sse_stream_memory_on(client):
    response = client.post("/api/incidents/INC-2045/triage?memory=on")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    body = response.text
    assert "event: thought" in body
    assert "event: tool_call" in body
    assert "event: recalled_memory" in body
    assert "event: warning" in body
    assert "event: suggestion" in body
    assert "event: done" in body
    assert "INC-1987" in body
    assert "Do NOT restart payments-db" in body


def test_triage_sse_stream_memory_off(client):
    response = client.post("/api/incidents/INC-2045/triage?memory=off")
    assert response.status_code == 200
    body = response.text
    
    assert "event: thought" in body
    assert "event: tool_call" in body
    assert "event: suggestion" in body
    assert "event: done" in body
    # Memory events must be suppressed in memory=off mode
    assert "event: recalled_memory" not in body
    assert "event: warning" not in body
    assert '"memory_augmented": false' in body.lower()


def test_feedback_endpoint_failed_outcome(client):
    payload = {
        "suggestion_id": "SUG-902",
        "outcome": "failed",
        "attempted_action": "systemctl restart postgresql",
        "note": "Restart cleared cache and caused 100% disk thrashing",
    }
    response = client.post("/api/incidents/INC-2045/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-2045"
    assert data["status"] == "recorded"
    assert data["negative_memory_retained"] is True


def test_feedback_endpoint_worked_outcome(client):
    payload = {
        "suggestion_id": "SUG-902",
        "outcome": "worked",
        "attempted_action": "Rollback checkout-api to v2.4.0",
        "note": "Latency dropped immediately back to 80ms baseline",
    }
    response = client.post("/api/incidents/INC-2045/feedback", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-2045"
    assert data["status"] == "recorded"
    assert data["negative_memory_retained"] is False


def test_feedback_endpoint_invalid_outcome(client):
    payload = {
        "suggestion_id": "SUG-902",
        "outcome": "invalid_outcome_string",
    }
    response = client.post("/api/incidents/INC-2045/feedback", json=payload)
    assert response.status_code == 422


def test_resolve_incident_endpoint(client):
    payload = {
        "root_cause": "Database connection pool exhaustion caused by unindexed query on orders.customer_id",
        "fix": "Rolled back v2.4.1 and applied PgBouncer pooler limit",
        "duration_min": 14,
    }
    response = client.post("/api/incidents/INC-2045/resolve", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-2045"
    assert data["status"] == "resolved"
    assert data["episodic_memory_retained"] is True


def test_get_incident_memories_endpoint(client):
    response = client.get("/api/incidents/INC-2045/memories")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_id"] == "INC-2045"
    assert data["count"] >= 1
    assert isinstance(data["memories"], list)


def test_get_observations_endpoint(client):
    response = client.get("/api/observations")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert data["source"] == "hindsight_reflect"
    assert isinstance(data["observations"], list)


def test_get_learning_curve_metrics_endpoint(client):
    response = client.get("/api/metrics/learning-curve")
    assert response.status_code == 200
    data = response.json()
    assert data["total_incidents_replayed"] == 40
    assert data["accuracy_memory_on"] > data["accuracy_memory_off"]
    assert data["avg_mttr_memory_on_min"] < data["avg_mttr_memory_off_min"]
    assert data["negative_fix_avoidance_rate"] == 1.0


def test_demo_reset_endpoint(client):
    payload = {"seed_days": 180}
    response = client.post("/api/demo/reset", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reset_complete"
    assert data["services_seeded"] == 8
    assert data["memories_seeded"] == 32


def test_mock_band_adapter():
    import asyncio
    adapter = MockBandAdapter(room_prefix="kartly-war-room")
    success = asyncio.run(
        adapter.post_incident_update(
            incident_id="INC-2045",
            message="Root cause identified: unindexed query on orders.customer_id",
            sender="Triage Agent",
        )
    )
    assert success is True
    assert len(adapter.messages_posted) == 1
    assert adapter.messages_posted[0]["incident_id"] == "INC-2045"
