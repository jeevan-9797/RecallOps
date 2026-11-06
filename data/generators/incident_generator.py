"""
RecallOps - Incident, Alert, Log Line & Fix Attempt Generator
Member 3: Database & Data Engineering

Generates 110 coherent incidents (INC-0001 to INC-0110) spanning 6 months,
with realistic alerts, 20-50 authentic operational logs per incident, and fix attempts.
"""

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from data.generators.root_causes import ROOT_CAUSE_FAMILIES


def generate_incidents_and_related_data(
    services: List[Dict[str, Any]],
    engineers: List[Dict[str, Any]],
    deployments: List[Dict[str, Any]],
    start_time: datetime,
    end_time: datetime,
    total_incidents: int = 110,
    seed: int = 42,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns: (alerts, incidents, log_lines, fix_attempts)
    Guarantees:
    - Exactly 110 incidents (INC-0001 to INC-0110)
    - 70 historical (INC-0001 to INC-0070)
    - 40 replay (INC-0071 to INC-0110)
    - All 8 root-cause families well-distributed across both datasets
    - 20-50 realistic logs per incident
    - 1-3 fix attempts per incident with worked/failed/partial outcomes
    """
    random.seed(seed)
    service_by_name = {s["name"]: s["id"] for s in services}
    engineer_ids = [e["id"] for e in engineers]
    family_keys = list(ROOT_CAUSE_FAMILIES.keys())

    # Distribute the 110 incidents across the 180-day timeline chronologically
    total_seconds = int((end_time - start_time).total_seconds())
    # Ensure chronological order with random spacing
    raw_offsets = sorted([random.randint(3600, total_seconds - 7200) for _ in range(total_incidents)])

    alerts: List[Dict[str, Any]] = []
    incidents: List[Dict[str, Any]] = []
    log_lines: List[Dict[str, Any]] = []
    fix_attempts: List[Dict[str, Any]] = []

    alert_id = 1
    log_id = 1
    fix_id = 1

    for idx, offset in enumerate(raw_offsets, start=1):
        code = f"INC-{idx:04d}"
        incident_time = start_time + timedelta(seconds=offset)
        
        # Round-robin + random perturbation to guarantee uniform coverage of all 8 root-cause families
        family_name = family_keys[(idx - 1) % len(family_keys)]
        family_def = ROOT_CAUSE_FAMILIES[family_name]

        # Select service associated with this family
        chosen_service_name = random.choice(family_def["services"])
        service_id = service_by_name[chosen_service_name]

        # Incident duration: between 18 and 115 minutes
        duration_min = random.randint(18, 115)
        resolved_time = incident_time + timedelta(minutes=duration_min)

        # Alert fires 1-5 minutes before incident is officially acknowledged
        alert_fired_time = incident_time - timedelta(minutes=random.randint(1, 5))
        alert_spec = family_def["alert"]
        metric_val = round(random.uniform(*alert_spec["value_range"]), 4)

        alert_payload = dict(alert_spec["payload_template"])
        alert_payload["service"] = chosen_service_name
        alert_payload["trigger_time"] = alert_fired_time.isoformat()

        alert_record = {
            "id": alert_id,
            "service_id": service_id,
            "metric": alert_spec["metric"],
            "threshold": alert_spec["threshold"],
            "value": metric_val,
            "fired_at": alert_fired_time,
            "payload": alert_payload,
        }
        alerts.append(alert_record)

        # Severity
        severity = random.choice(family_def["severities"])

        # Root cause text
        root_cause_detail = f"{family_def['root_cause_summary']} Impacted service: {chosen_service_name}."

        incident_record = {
            "id": idx,
            "code": code,
            "alert_id": alert_id,
            "severity": severity,
            "status": "RESOLVED",
            "opened_at": incident_time,
            "resolved_at": resolved_time,
            "root_cause": root_cause_detail,
            "root_cause_family": family_name,
            "duration_min": duration_min,
        }
        incidents.append(incident_record)
        alert_id += 1

        # Generate 20 to 50 realistic log lines for this incident
        num_logs = random.randint(22, 48)
        log_start = alert_fired_time - timedelta(minutes=2)
        log_window_seconds = int((resolved_time - log_start).total_seconds())

        # Select log templates for this family
        template_messages = family_def["log_messages"]

        for _ in range(num_logs):
            log_ts = log_start + timedelta(seconds=random.randint(0, max(log_window_seconds, 60)))
            level, default_src, msg = random.choice(template_messages)
            
            # Occasionally add specific details to message
            custom_msg = msg
            if "{service}" in custom_msg:
                custom_msg = custom_msg.replace("{service}", chosen_service_name)
                
            log_lines.append({
                "id": log_id,
                "incident_id": idx,
                "ts": log_ts,
                "level": level,
                "source": default_src,
                "message": custom_msg,
            })
            log_id += 1

        # Generate realistic fix attempts
        # Sequence: either 1 worked fix, or 1 failed + 1 worked, or 1 failed + 1 partial + 1 worked
        chosen_engineer = random.choice(engineer_ids)
        num_attempts = random.choice([1, 2, 2, 3])

        if num_attempts == 1:
            # Direct resolution
            fix_time = incident_time + timedelta(minutes=duration_min - 2)
            fix_attempts.append({
                "id": fix_id,
                "incident_id": idx,
                "action": random.choice(family_def["worked_fixes"]),
                "outcome": "worked",
                "by_engineer": chosen_engineer,
                "at": fix_time,
            })
            fix_id += 1
        elif num_attempts == 2:
            # First failed, then worked
            first_fail_time = incident_time + timedelta(minutes=int(duration_min * 0.3))
            fix_attempts.append({
                "id": fix_id,
                "incident_id": idx,
                "action": random.choice(family_def["failed_fixes"]),
                "outcome": "failed",
                "by_engineer": chosen_engineer,
                "at": first_fail_time,
            })
            fix_id += 1

            second_work_time = incident_time + timedelta(minutes=duration_min - 2)
            fix_attempts.append({
                "id": fix_id,
                "incident_id": idx,
                "action": random.choice(family_def["worked_fixes"]),
                "outcome": "worked",
                "by_engineer": random.choice(engineer_ids),
                "at": second_work_time,
            })
            fix_id += 1
        else:
            # 1 failed, 1 partial, 1 worked
            t1 = incident_time + timedelta(minutes=int(duration_min * 0.25))
            t2 = incident_time + timedelta(minutes=int(duration_min * 0.60))
            t3 = incident_time + timedelta(minutes=duration_min - 2)

            fix_attempts.append({
                "id": fix_id,
                "incident_id": idx,
                "action": random.choice(family_def["failed_fixes"]),
                "outcome": "failed",
                "by_engineer": chosen_engineer,
                "at": t1,
            })
            fix_id += 1

            fix_attempts.append({
                "id": fix_id,
                "incident_id": idx,
                "action": random.choice(family_def["partial_fixes"]),
                "outcome": "partial",
                "by_engineer": random.choice(engineer_ids),
                "at": t2,
            })
            fix_id += 1

            fix_attempts.append({
                "id": fix_id,
                "incident_id": idx,
                "action": random.choice(family_def["worked_fixes"]),
                "outcome": "worked",
                "by_engineer": random.choice(engineer_ids),
                "at": t3,
            })
            fix_id += 1

    return alerts, incidents, log_lines, fix_attempts
