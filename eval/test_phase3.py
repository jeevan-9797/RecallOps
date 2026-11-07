"""
Unit Tests for Phase 3: Learning Proof & Replay Evaluation Harness
Author: Member 4 (AI/ML & Model)
Phase: Phase 3: Learning Proof (H16–H22)
"""

import json
from pathlib import Path
import pytest

from eval.replay_harness import (
    ReplayHarness,
    generate_held_out_incidents,
    evaluate_hypothesis_semantic_match,
)
from eval.export_metrics import export_metrics_and_charts


# ==============================================================================
# 1. DATASET INTEGRITY TESTS
# ==============================================================================

def test_held_out_incidents_generation():
    incidents = generate_held_out_incidents()
    assert len(incidents) == 40

    first_inc = incidents[0]
    last_inc = incidents[-1]

    assert first_inc.incident_num == 1
    assert first_inc.incident_id == "INC-071"
    assert last_inc.incident_num == 40
    assert last_inc.incident_id == "INC-110"

    expected_services = {
        "payments-db",
        "cart-service",
        "checkout-api",
        "ingress-gateway",
        "order-worker",
        "inventory-service",
        "auth-service",
        "billing-service",
    }
    actual_services = {inc.service_name for inc in incidents}
    assert expected_services.issubset(actual_services)

    for inc in incidents:
        assert inc.ground_truth_root_cause
        assert inc.successful_fix
        assert len(inc.known_failed_fixes) >= 1
        assert len(inc.key_terms) >= 3
        assert inc.baseline_minutes > inc.optimized_minutes


# ==============================================================================
# 2. SEMANTIC EVALUATION JUDGE TESTS
# ==============================================================================

def test_semantic_evaluation_judge_matching():
    ground_truth = "HikariCP connection pool exhaustion caused by unclosed ResultSet in PaymentGatewayClient"
    hypothesis = "HikariCP connection pool exhaustion due to leaked connection ResultSet"
    key_terms = ["hikaricp", "connection", "pool", "exhaustion", "resultset"]

    res = evaluate_hypothesis_semantic_match(hypothesis, ground_truth, key_terms)
    assert res.is_match is True
    assert res.score >= 0.60


def test_semantic_evaluation_judge_mismatch():
    ground_truth = "HikariCP connection pool exhaustion caused by unclosed ResultSet in PaymentGatewayClient"
    irrelevant_hypothesis = "Expired TLS SSL certificate on ingress controller"
    key_terms = ["hikaricp", "connection", "pool", "exhaustion", "resultset"]

    res = evaluate_hypothesis_semantic_match(irrelevant_hypothesis, ground_truth, key_terms)
    assert res.is_match is False
    assert res.score < 0.20


# ==============================================================================
# 3. REPLAY HARNESS LEARNING CURVE VERIFICATION
# ==============================================================================

def test_replay_harness_learning_curve():
    harness = ReplayHarness()

    report_off = harness.run_evaluation(memory_enabled=False)
    report_on = harness.run_evaluation(memory_enabled=True)

    # 1. Accuracy comparison: Memory ON must dramatically outperform Memory OFF
    assert report_on.final_top_1_accuracy >= 0.70
    assert report_off.final_top_1_accuracy <= 0.45
    accuracy_delta = report_on.final_top_1_accuracy - report_off.final_top_1_accuracy
    assert accuracy_delta >= 0.35  # At least 35% accuracy improvement

    # 2. MTTR comparison: Memory ON must be significantly faster
    assert report_on.average_minutes_to_hypothesis < report_off.average_minutes_to_hypothesis
    mttr_reduction = (
        (report_off.average_minutes_to_hypothesis - report_on.average_minutes_to_hypothesis)
        / report_off.average_minutes_to_hypothesis
    )
    assert mttr_reduction >= 0.40  # At least 40% MTTR reduction

    # 3. Repeated failed fix comparison: Memory ON must have 0 anti-pattern violations
    assert report_on.total_failed_fix_violations == 0
    assert report_off.total_failed_fix_violations > 10


# ==============================================================================
# 4. EXPORT CONTRACT INTEGRITY TESTS
# ==============================================================================

def test_exported_files_contract():
    eval_dir = Path(__file__).resolve().parent
    chart_file = eval_dir / "chart_data.json"
    headline_file = eval_dir / "headline_metrics.json"
    results_file = eval_dir / "replay_results.json"

    # Run export
    export_metrics_and_charts(
        replay_results_path=results_file,
        chart_data_path=chart_file,
        headline_metrics_path=headline_file,
    )

    assert results_file.exists()
    assert chart_file.exists()
    assert headline_file.exists()

    # Verify chart_data.json
    with open(chart_file, "r", encoding="utf-8") as f:
        chart_data = json.load(f)

    assert isinstance(chart_data, list)
    assert len(chart_data) == 40
    sample = chart_data[0]
    required_keys = {
        "incident_num",
        "incident_id",
        "service_name",
        "memory_on_accuracy",
        "memory_off_accuracy",
        "memory_on_mttr",
        "memory_off_mttr",
        "failed_fixes_repeated_on",
        "failed_fixes_repeated_off",
    }
    assert required_keys.issubset(sample.keys())

    # Verify monotonic / learning progression in chart_data
    # Memory ON accuracy should be higher at the end than at the start
    assert chart_data[-1]["memory_on_accuracy"] > chart_data[0]["memory_on_accuracy"]
    # MTTR should be lower at the end than at the start
    assert chart_data[-1]["memory_on_mttr"] < chart_data[0]["memory_on_mttr"]
    # Zero violations with memory ON
    assert chart_data[-1]["failed_fixes_repeated_on"] == 0

    # Verify headline_metrics.json
    with open(headline_file, "r", encoding="utf-8") as f:
        headlines = json.load(f)

    assert "headline_1_accuracy" in headlines
    assert "headline_2_mttr" in headlines
    assert "headline_3_anti_patterns" in headlines

    assert "+" in headlines["headline_1_accuracy"]["delta"]
    assert "%" in headlines["headline_2_mttr"]["reduction_percentage"]
    assert headlines["headline_3_anti_patterns"]["violations_memory_on"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
