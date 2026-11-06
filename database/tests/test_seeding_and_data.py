"""
RecallOps - Seeding & Data Generation Tests
Member 3: Database & Data Engineering
"""

import pytest
from datetime import datetime
from data.generators.dataset_builder import build_complete_dataset
from data.validate_data import validate_dataset


def test_dataset_generation_counts():
    """Verify total counts for all Kartly entities and operational records."""
    dataset = build_complete_dataset(seed=42)
    
    assert len(dataset["services"]) == 6
    assert len(dataset["engineers"]) == 8
    assert len(dataset["deploys"]) == 400
    assert len(dataset["incidents"]) == 110
    assert len(dataset["historical_incidents"]) == 70
    assert len(dataset["held_out_incidents"]) == 40
    assert len(dataset["alerts"]) == 110
    assert len(dataset["log_lines"]) >= 2200
    assert len(dataset["fix_attempts"]) >= 110


def test_root_cause_family_coverage():
    """Ensure at least 8 distinct root cause families exist in both historical and replay splits."""
    dataset = build_complete_dataset(seed=42)
    
    hist_families = set(i["root_cause_family"] for i in dataset["historical_incidents"])
    replay_families = set(i["root_cause_family"] for i in dataset["held_out_incidents"])
    
    assert len(hist_families) >= 8, f"Historical only has {len(hist_families)} families"
    assert len(replay_families) >= 8, f"Replay only has {len(replay_families)} families"
    
    required_families = {
        "db_pool",
        "redis_eviction",
        "tls_expiry",
        "payment_timeout",
        "feature_flag",
        "disk_full",
        "n_plus_one",
        "kafka_lag",
    }
    assert required_families.issubset(hist_families)
    assert required_families.issubset(replay_families)


def test_strict_dataset_partition_boundaries():
    """Verify strictly no overlap or leakage between historical (1-70) and replay (71-110)."""
    dataset = build_complete_dataset(seed=42)
    hist_ids = [i["id"] for i in dataset["historical_incidents"]]
    replay_ids = [i["id"] for i in dataset["held_out_incidents"]]
    
    assert min(hist_ids) == 1
    assert max(hist_ids) == 70
    assert min(replay_ids) == 71
    assert max(replay_ids) == 110
    assert set(hist_ids).isdisjoint(set(replay_ids))


def test_fix_attempt_outcomes():
    """Verify fix attempt outcomes strictly conform to 'worked', 'failed', 'partial'."""
    dataset = build_complete_dataset(seed=42)
    valid_outcomes = {"worked", "failed", "partial"}
    
    outcomes = set(f["outcome"] for f in dataset["fix_attempts"])
    assert outcomes.issubset(valid_outcomes)
    assert "worked" in outcomes
    assert "failed" in outcomes
    assert "partial" in outcomes


def test_validation_suite_pass():
    """Verify that validate_dataset returns True with 0 errors."""
    passed, errors, metrics = validate_dataset()
    assert passed, f"Validation failed with: {errors}"
    assert metrics["status"] == "PASSED"


def test_duplicate_seeding_prevention():
    """Verify that running seed_postgres without reset safely skips existing records."""
    from sqlalchemy import create_engine
    from data.seed_postgres import seed_postgres

    test_eng = create_engine("sqlite:///:memory:")
    # First seed initializes and seeds
    r1 = seed_postgres(engine=test_eng, reset_first=True)
    assert r1["incidents"] == 110

    # Second seed with reset_first=False must detect existing data and skip without error
    r2 = seed_postgres(engine=test_eng, reset_first=False)
    assert r2["status"] == "skipped"
    assert r2["reason"] == "already_seeded"
    assert r2["incidents"] == 110
