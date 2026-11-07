"""
Unit and Integration Tests for Learning Curve Metrics API (Phase P4B).
Validates:
1. HTTP 200 response and payload structure.
2. Exact 40-point learning-curve series.
3. Strict mapping of point fields (n, on, off) and stats (top1_on, top1_off, repeated_failed_fixes_on).
4. Backward-compatible scalar fields for legacy backend consumers.
5. Graceful handling of missing files (HTTP 503).
6. Graceful handling of malformed JSON / schemas (HTTP 500).
7. Dependency-injection overrides with isolated temp files.
8. Preservation of frozen agent contracts.
"""

import json
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.api.metrics import (
    DEFAULT_CHART_DATA_PATH,
    DEFAULT_HEADLINE_METRICS_PATH,
    get_learning_curve_data,
    load_learning_curve_metrics,
)
from backend.app.main import app
from backend.app.schemas.agent_tools import (
    AgentTriageResponse,
    get_openai_tool_definitions,
)
from backend.app.schemas.api_models import (
    LearningCurveMetricsResponse,
    LearningCurvePoint,
    LearningCurveStats,
)


# ==============================================================================
# 1. LIVE ENDPOINT CONTRACT TESTS
# ==============================================================================

def test_get_learning_curve_metrics_endpoint_success(client: TestClient):
    """Verifies that GET /api/metrics/learning-curve returns HTTP 200 with dual contract."""
    response = client.get("/api/metrics/learning-curve")
    assert response.status_code == 200
    data = response.json()

    # Frontend LearningCurve contract verification
    assert "points" in data
    assert "stats" in data
    assert isinstance(data["points"], list)
    assert len(data["points"]) == 40
    assert data["sample"] is False

    # Point 1 (n=1) validation
    first = data["points"][0]
    assert first["n"] == 1
    assert "on" in first
    assert "off" in first
    assert 0.0 <= first["on"] <= 1.0
    assert 0.0 <= first["off"] <= 1.0

    # Point 40 (n=40) validation
    last = data["points"][39]
    assert last["n"] == 40
    assert last["on"] == 0.8
    assert last["off"] == 0.325

    # Stats validation
    stats = data["stats"]
    assert stats["top1_on"] == 0.8
    assert stats["top1_off"] == 0.325
    assert stats["repeated_failed_fixes_on"] == 0
    assert stats["repeated_failed_fixes_off"] == 23
    assert stats["avg_mttr_on_min"] == 21.1
    assert stats["avg_mttr_off_min"] == 45.0

    # Backward-compatible backend top-level fields
    assert data["total_incidents_replayed"] == 40
    assert data["accuracy_memory_on"] == 0.8
    assert data["accuracy_memory_off"] == 0.325
    assert data["avg_mttr_memory_on_min"] == 21.1
    assert data["avg_mttr_memory_off_min"] == 45.0
    assert data["negative_fix_avoidance_rate"] == 1.0
    assert "benchmark" in data["benchmark_status"]


def test_learning_curve_point_monotonicity_and_fields(client: TestClient):
    """Verifies all 40 points conform strictly to schema and monotonically increase n."""
    response = client.get("/api/metrics/learning-curve")
    assert response.status_code == 200
    points = response.json()["points"]

    assert len(points) == 40
    for idx, p in enumerate(points, start=1):
        assert p["n"] == idx
        assert isinstance(p["on"], float)
        assert isinstance(p["off"], float)
        assert 0.0 <= p["on"] <= 1.0
        assert 0.0 <= p["off"] <= 1.0


# ==============================================================================
# 2. ISOLATED ERROR HANDLING TESTS (TEMP FILES)
# ==============================================================================

def test_missing_chart_data_file_raises_503(tmp_path: Path):
    """Missing chart_data.json must raise HTTP 503 Service Unavailable."""
    missing_chart = tmp_path / "non_existent_chart.json"
    headline_file = tmp_path / "headline.json"
    headline_file.write_text(json.dumps({"dummy": 1}))

    with pytest.raises(HTTPException) as exc_info:
        load_learning_curve_metrics(chart_path=missing_chart, headline_path=headline_file)

    assert exc_info.value.status_code == 503
    assert "not found" in exc_info.value.detail


def test_missing_headline_metrics_file_raises_503(tmp_path: Path):
    """Missing headline_metrics.json must raise HTTP 503 Service Unavailable."""
    chart_file = tmp_path / "chart.json"
    chart_file.write_text(json.dumps([]))
    missing_headline = tmp_path / "non_existent_headline.json"

    with pytest.raises(HTTPException) as exc_info:
        load_learning_curve_metrics(chart_path=chart_file, headline_path=missing_headline)

    assert exc_info.value.status_code == 503
    assert "not found" in exc_info.value.detail


def test_malformed_json_in_chart_file_raises_500(tmp_path: Path):
    """Corrupted JSON in chart file must raise HTTP 500."""
    bad_chart = tmp_path / "chart.json"
    bad_chart.write_text("{ incomplete json ...")
    headline_file = tmp_path / "headline.json"
    headline_file.write_text(json.dumps({"dummy": 1}))

    with pytest.raises(HTTPException) as exc_info:
        load_learning_curve_metrics(chart_path=bad_chart, headline_path=headline_file)

    assert exc_info.value.status_code == 500
    assert "Malformed" in exc_info.value.detail


def test_malformed_json_in_headline_file_raises_500(tmp_path: Path):
    """Corrupted JSON in headline file must raise HTTP 500."""
    valid_chart = tmp_path / "chart.json"
    valid_chart.write_text(json.dumps([]))
    bad_headline = tmp_path / "headline.json"
    bad_headline.write_text("NOT JSON AT ALL")

    with pytest.raises(HTTPException) as exc_info:
        load_learning_curve_metrics(chart_path=valid_chart, headline_path=bad_headline)

    assert exc_info.value.status_code == 500
    assert "Malformed" in exc_info.value.detail


def test_missing_headline_schema_keys_raises_500(tmp_path: Path):
    """Valid JSON missing required headline metric fields must raise HTTP 500."""
    valid_chart = tmp_path / "chart.json"
    valid_chart.write_text(json.dumps([{"incident_num": 1, "on": 0.5, "off": 0.5}]))
    incomplete_headline = tmp_path / "headline.json"
    incomplete_headline.write_text(json.dumps({"unexpected_root": {}}))

    with pytest.raises(HTTPException) as exc_info:
        load_learning_curve_metrics(chart_path=valid_chart, headline_path=incomplete_headline)

    assert exc_info.value.status_code == 500
    assert "Invalid schema" in exc_info.value.detail


# ==============================================================================
# 3. DEPENDENCY INJECTION & OVERRIDE TEST
# ==============================================================================

def test_endpoint_dependency_injection_override(client: TestClient, tmp_path: Path):
    """Verifies that FastAPI dependency injection allows custom metrics loading."""
    mock_chart = tmp_path / "custom_chart.json"
    mock_chart.write_text(
        json.dumps(
            [
                {"incident_num": 1, "memory_on_accuracy": 0.5, "memory_off_accuracy": 0.2},
                {"incident_num": 2, "memory_on_accuracy": 0.75, "memory_off_accuracy": 0.25},
            ]
        )
    )

    mock_headline = tmp_path / "custom_headline.json"
    mock_headline.write_text(
        json.dumps(
            {
                "headline_1_accuracy": {"stat": "75.0%", "baseline": "25.0%"},
                "headline_2_mttr": {"stat": "15.0 min", "baseline": "30.0 min"},
                "headline_3_anti_patterns": {
                    "stat": "100.0%",
                    "violations_memory_on": 0,
                    "violations_memory_off": 5,
                },
            }
        )
    )

    def custom_loader():
        return load_learning_curve_metrics(chart_path=mock_chart, headline_path=mock_headline)

    app.dependency_overrides[get_learning_curve_data] = custom_loader
    try:
        resp = client.get("/api/metrics/learning-curve")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["points"]) == 2
        assert data["points"][0]["n"] == 1
        assert data["points"][1]["on"] == 0.75
        assert data["stats"]["top1_on"] == 0.75
        assert data["stats"]["top1_off"] == 0.25
        assert data["total_incidents_replayed"] == 2
    finally:
        app.dependency_overrides.pop(get_learning_curve_data, None)


# ==============================================================================
# 4. CONTRACT INTEGRITY AUDIT TEST
# ==============================================================================

def test_frozen_contracts_remain_intact():
    """Confirms that modifying api_models.py did not alter frozen agent contracts."""
    tools = get_openai_tool_definitions()
    assert len(tools) == 6
    tool_names = {t["function"]["name"] for t in tools}
    assert tool_names == {
        "recall_similar_incidents",
        "recall_failed_fixes",
        "get_recent_deploys",
        "get_logs",
        "get_service_owner",
        "post_to_band_room",
    }

    # Verify AgentTriageResponse strict extra="forbid" behavior
    valid_payload = {
        "incident_id": "INC-071",
        "hypothesis": "Connection leak in payments-db [INC-1987]",
        "confidence": 0.95,
        "cited_incident_ids": ["INC-1987"],
        "failed_fixes_warning": ["Do NOT restart database"],
        "recommended_action": "Tune pool ceiling to 40",
        "likely_owner": "payments-squad",
    }
    resp = AgentTriageResponse(**valid_payload)
    assert resp.incident_id == "INC-071"
    assert resp.confidence == 0.95

    # Confirm extra fields are forbidden
    with pytest.raises(Exception):
        AgentTriageResponse(**{**valid_payload, "extra_unexpected_field": "invalid"})
