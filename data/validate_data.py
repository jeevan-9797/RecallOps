"""
RecallOps - Comprehensive Data & Integrity Validator
Member 3: Database & Data Engineering

Validates all operational constraints, referential integrity, historical vs replay separation,
log volumes, and failure pattern distributions.
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.generators.dataset_builder import build_complete_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("validate_data")


def validate_dataset() -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Executes a comprehensive battery of validation tests.
    Returns: (all_passed: bool, errors: List[str], metrics: Dict[str, Any])
    """
    errors: List[str] = []
    dataset = build_complete_dataset(seed=42)

    engineers = dataset["engineers"]
    services = dataset["services"]
    deploys = dataset["deploys"]
    alerts = dataset["alerts"]
    incidents = dataset["incidents"]
    log_lines = dataset["log_lines"]
    fix_attempts = dataset["fix_attempts"]
    historical = dataset["historical_incidents"]
    held_out = dataset["held_out_incidents"]

    # 1. Engineers
    if len(engineers) != 8:
        errors.append(f"Expected 8 engineers, found {len(engineers)}")
    for eng in engineers:
        if not eng.get("slack_handle") or not eng["slack_handle"].startswith("@"):
            errors.append(f"Engineer {eng.get('name')} missing valid Slack handle")

    # 2. Services
    if len(services) != 6:
        errors.append(f"Expected 6 services, found {len(services)}")
    expected_services = {"checkout-api", "payments-svc", "inventory-svc", "search-svc", "notification-svc", "delivery-eta-svc"}
    actual_services = set(s["name"] for s in services)
    if expected_services != actual_services:
        errors.append(f"Service name mismatch: {expected_services - actual_services}")

    # 3. Deployments
    if len(deploys) < 380 or len(deploys) > 420:
        errors.append(f"Expected ~400 deployments, found {len(deploys)}")

    # 4. Incidents
    if len(incidents) != 110:
        errors.append(f"Expected 110 incidents, found {len(incidents)}")

    # 5. Incident Codes & Uniqueness
    codes = [inc["code"] for inc in incidents]
    if len(set(codes)) != 110:
        errors.append("Duplicate incident codes detected")
    for i, code in enumerate(codes, start=1):
        expected_code = f"INC-{i:04d}"
        if code != expected_code:
            errors.append(f"Incident index {i} has unexpected code: {code} (expected {expected_code})")

    # 6. Historical vs Held-Out Replay Split
    if len(historical) != 70:
        errors.append(f"Expected 70 historical incidents, found {len(historical)}")
    if len(held_out) != 40:
        errors.append(f"Expected 40 held-out replay incidents, found {len(held_out)}")

    historical_ids = set(inc["id"] for inc in historical)
    held_out_ids = set(inc["id"] for inc in held_out)
    if historical_ids.intersection(held_out_ids):
        errors.append("Collision detected between historical and held-out replay IDs")
    if max(historical_ids) != 70 or min(held_out_ids) != 71:
        errors.append("Strict boundary violation between historical (1-70) and replay (71-110)")

    # 7. Root-Cause Families Coverage
    families = set(inc["root_cause_family"] for inc in incidents)
    if len(families) < 8:
        errors.append(f"Expected at least 8 root-cause families, found {len(families)}")
    
    # Check that both historical and replay cover all families
    hist_families = set(inc["root_cause_family"] for inc in historical)
    replay_families = set(inc["root_cause_family"] for inc in held_out)
    if len(hist_families) < 8:
        errors.append(f"Historical dataset missing root cause families: {8 - len(hist_families)}")
    if len(replay_families) < 8:
        errors.append(f"Replay dataset missing root cause families: {8 - len(replay_families)}")

    # 8. Alert and Incident Timestamp Integrity
    alert_by_id = {a["id"]: a for a in alerts}
    for inc in incidents:
        alert = alert_by_id.get(inc.get("alert_id"))
        if not alert:
            errors.append(f"Incident {inc['code']} missing associated alert")
        else:
            if alert["fired_at"] > inc["opened_at"]:
                errors.append(f"Alert fired ({alert['fired_at']}) after incident opened ({inc['opened_at']})")
        if inc["resolved_at"] and inc["resolved_at"] < inc["opened_at"]:
            errors.append(f"Incident {inc['code']} resolved before opened")

    # 9. Log Line Volume & Association
    logs_by_inc: Dict[int, List[Dict[str, Any]]] = {}
    for log in log_lines:
        logs_by_inc.setdefault(log["incident_id"], []).append(log)
    
    for inc in incidents:
        inc_logs = logs_by_inc.get(inc["id"], [])
        if len(inc_logs) < 20 or len(inc_logs) > 50:
            errors.append(f"Incident {inc['code']} has {len(inc_logs)} logs (expected 20-50)")

    # 10. Fix Attempts Integrity
    valid_outcomes = {"worked", "failed", "partial"}
    fixes_by_inc: Dict[int, List[Dict[str, Any]]] = {}
    for fix in fix_attempts:
        fixes_by_inc.setdefault(fix["incident_id"], []).append(fix)
        if fix["outcome"] not in valid_outcomes:
            errors.append(f"Fix attempt {fix['id']} has invalid outcome: {fix['outcome']}")

    for inc in incidents:
        inc_fixes = fixes_by_inc.get(inc["id"], [])
        if not inc_fixes:
            errors.append(f"Incident {inc['code']} has no fix attempts")
        elif not any(f["outcome"] == "worked" for f in inc_fixes):
            errors.append(f"Resolved incident {inc['code']} missing a 'worked' fix attempt")

    all_passed = len(errors) == 0

    metrics = {
        "engineers": len(engineers),
        "services": len(services),
        "deployments": len(deploys),
        "total_incidents": len(incidents),
        "historical_incidents": len(historical),
        "held_out_incidents": len(held_out),
        "root_cause_families": len(families),
        "total_alerts": len(alerts),
        "total_log_lines": len(log_lines),
        "avg_logs_per_incident": round(len(log_lines) / len(incidents), 1),
        "total_fix_attempts": len(fix_attempts),
        "status": "PASSED" if all_passed else "FAILED",
    }

    return all_passed, errors, metrics


def print_report():
    print("=" * 70)
    print("RECALLOPS - DATA INTEGRITY & VALIDATION REPORT")
    print("=" * 70)

    passed, errors, metrics = validate_dataset()

    print("\n[VALIDATION METRICS SCORECARD]")
    for k, v in metrics.items():
        print(f"  * {k.replace('_', ' ').title():<28}: {v}")

    print("\n[TEST RESULTS]")
    if passed:
        print("  >>> ALL 10 INTEGRITY CHECKS PASSED SUCCESSFULLY. <<<")
    else:
        print(f"  >>> FAILED WITH {len(errors)} ERROR(S): <<<")
        for err in errors[:15]:
            print(f"    - {err}")
        if len(errors) > 15:
            print(f"    ... and {len(errors) - 15} more errors")

    print("=" * 70)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(print_report())
