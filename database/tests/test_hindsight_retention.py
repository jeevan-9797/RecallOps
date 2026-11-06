"""
RecallOps - Hindsight Seeding & Safety Tests
Member 3: Database & Data Engineering
"""

import pytest
from data.generators.dataset_builder import build_complete_dataset
from data.seed_hindsight import format_incident_memory, seed_hindsight


def test_memory_format_structure():
    """Verify memory formatting matches the agreed template."""
    sample_incident = {
        "id": 1,
        "code": "INC-0001",
        "severity": "P1",
        "root_cause_family": "db_pool",
        "root_cause": "HikariCP connection pool exhausted due to unclosed sessions.",
        "duration_min": 35,
    }
    sample_alert = {
        "metric": "db_connection_pool_active_ratio",
        "value": 0.98,
        "threshold": 0.90,
    }
    sample_deploy = {
        "summary": "perf(db): tune pool size",
        "config_change": True,
    }
    sample_fixes = [
        {"action": "Restart pods", "outcome": "failed"},
        {"action": "Increase HikariCP maximumPoolSize to 65", "outcome": "worked"},
    ]

    formatted = format_incident_memory(
        incident=sample_incident,
        service_name="checkout-api",
        alert_info=sample_alert,
        recent_deploy=sample_deploy,
        fix_attempts=sample_fixes,
    )

    assert "[INC-0001]" in formatted
    assert "[checkout-api]" in formatted
    assert "[family: db_pool]" in formatted
    assert "Symptom:" in formatted
    assert "Deployment:" in formatted
    assert "Failed fix:" in formatted
    assert "Outcome:\nFAILED." in formatted
    assert "Successful fix:" in formatted
    assert "Outcome:\nWORKED." in formatted
    assert "Resolution time:\n35 minutes." in formatted


def test_no_replay_incidents_in_hindsight():
    """Verify that seed_hindsight only processes incidents 1-70 and never 71-110."""
    res = seed_hindsight(dry_run=True)
    assert res["historical_retained"] == 70
    assert res["replay_held_out"] == 40
    assert res["mode"] == "dry_run"
