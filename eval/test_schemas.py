"""
Unit Tests for RecallOps Schemas, Contracts, and Tool Definitions
Validates Pydantic v2 schemas and JSON hand-off contract.
"""

import json
import pytest
from pathlib import Path
from pydantic import ValidationError

from backend.app.schemas.agent_tools import (
    RecallSimilarIncidentsInput,
    RecallFailedFixesInput,
    GetRecentDeploysInput,
    GetLogsInput,
    GetServiceOwnerInput,
    PostToBandRoomInput,
    AgentTriageResponse,
    get_openai_tool_definitions,
    get_agent_response_schema,
)


def test_recall_similar_incidents_validation():
    # Valid
    valid = RecallSimilarIncidentsInput(service_name="checkout-api", symptom="OOM crash", limit=5)
    assert valid.service_name == "checkout-api"
    assert valid.limit == 5

    # Defaults
    default_obj = RecallSimilarIncidentsInput(service_name="payments-db", symptom="Connection pool full")
    assert default_obj.limit == 3

    # Invalid limit (negative or 0)
    with pytest.raises(ValidationError):
        RecallSimilarIncidentsInput(service_name="auth", symptom="500", limit=0)

    # Missing required field
    with pytest.raises(ValidationError):
        RecallSimilarIncidentsInput(service_name="auth")  # type: ignore


def test_recall_failed_fixes_validation():
    valid = RecallFailedFixesInput(
        service_name="payments-db",
        incident_signature="FATAL: remaining connection slots are reserved",
    )
    assert valid.service_name == "payments-db"
    assert "connection slots" in valid.incident_signature

    with pytest.raises(ValidationError):
        RecallFailedFixesInput(service_name="payments-db")  # type: ignore


def test_get_recent_deploys_validation():
    valid = GetRecentDeploysInput(service_name="orders-worker", lookback_hours=48)
    assert valid.lookback_hours == 48

    # Default
    default_obj = GetRecentDeploysInput(service_name="orders-worker")
    assert default_obj.lookback_hours == 24


def test_get_logs_validation():
    valid = GetLogsInput(service_name="ingress-gateway", incident_id="INC-1001", limit=100)
    assert valid.service_name == "ingress-gateway"
    assert valid.limit == 100

    default_obj = GetLogsInput(service_name="ingress-gateway", incident_id="INC-1001")
    assert default_obj.limit == 50


def test_get_service_owner_validation():
    valid = GetServiceOwnerInput(service_name="auth-service")
    assert valid.service_name == "auth-service"


def test_post_to_band_room_validation():
    valid = PostToBandRoomInput(incident_id="INC-2045", message="Investigating DB deadlock")
    assert valid.sender == "Triage Agent"

    custom = PostToBandRoomInput(incident_id="INC-2045", message="Fixed", sender="Lead SRE")
    assert custom.sender == "Lead SRE"


def test_agent_triage_response_valid():
    response = AgentTriageResponse(
        incident_id="INC-2045",
        hypothesis="Threadpool starvation caused by unindexed query on transactions table",
        confidence=0.95,
        cited_incident_ids=["INC-1987", "INC-1754"],
        failed_fixes_warning=["Do NOT restart payments-db: failed 2x in Sept"],
        recommended_action="Apply index migration idx_tx_customer and scale read replicas",
        likely_owner="payments-platform-team",
    )
    assert response.confidence == 0.95
    assert len(response.cited_incident_ids) == 2
    assert len(response.failed_fixes_warning) == 1
    assert "payments-db" in response.failed_fixes_warning[0]


def test_agent_triage_response_confidence_bounds():
    # Confidence > 1.0 must fail
    with pytest.raises(ValidationError):
        AgentTriageResponse(
            incident_id="INC-1",
            hypothesis="Test",
            confidence=1.5,
            recommended_action="Test",
            likely_owner="Test",
        )

    # Confidence < 0.0 must fail
    with pytest.raises(ValidationError):
        AgentTriageResponse(
            incident_id="INC-1",
            hypothesis="Test",
            confidence=-0.1,
            recommended_action="Test",
            likely_owner="Test",
        )


def test_agent_triage_response_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        AgentTriageResponse(
            incident_id="INC-1",
            hypothesis="Test",
            confidence=0.8,
            recommended_action="Test",
            likely_owner="Test",
            unauthorized_extra_field="malicious",  # type: ignore
        )


def test_openai_tool_definitions_structure():
    tools = get_openai_tool_definitions()
    assert len(tools) == 6

    expected_tool_names = {
        "recall_similar_incidents",
        "recall_failed_fixes",
        "get_recent_deploys",
        "get_logs",
        "get_service_owner",
        "post_to_band_room",
    }
    extracted_names = {t["function"]["name"] for t in tools}
    assert extracted_names == expected_tool_names

    for t in tools:
        assert t["type"] == "function"
        fn = t["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]
        assert "required" in fn["parameters"]


def test_hand_off_contract_json_file():
    contract_file = Path(__file__).resolve().parent / "hand_off_contract.json"
    assert contract_file.exists(), "hand_off_contract.json must exist in /eval"

    with open(contract_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) == 6

    names = [tool["function"]["name"] for tool in data]
    assert "recall_similar_incidents" in names
    assert "recall_failed_fixes" in names
    assert "get_recent_deploys" in names
    assert "get_logs" in names
    assert "get_service_owner" in names
    assert "post_to_band_room" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
