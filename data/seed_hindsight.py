"""
RecallOps - Hindsight Cloud Memory Seeder
Member 3: Database & Data Engineering

Retains historical incident summaries (INC-0001 through INC-0070) into Hindsight memory bank 'kartly-sre'.
STRICT RULES:
- Replay incidents (INC-0071 through INC-0110) are strictly excluded from Hindsight!
- NEVER store raw operational log lines in Hindsight.
- Supports live API retention and verified mock/dry-run retention.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.generators.dataset_builder import build_complete_dataset

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_hindsight")


def format_incident_memory(
    incident: Dict[str, Any],
    service_name: str,
    alert_info: Optional[Dict[str, Any]],
    recent_deploy: Optional[Dict[str, Any]],
    fix_attempts: List[Dict[str, Any]],
) -> str:
    """
    Format incident memory text according to the agreed RecallOps template:
    [INC-xxxx]
    [<service>]
    [family: <root_cause_family>]

    Symptom:
    ...
    Deployment:
    ...
    Failed fix:
    ...
    Outcome:
    FAILED.
    Root cause:
    ...
    Successful fix:
    ...
    Outcome:
    WORKED.
    Resolution time:
    ...
    """
    code = incident["code"]
    family = incident["root_cause_family"]
    root_cause = incident["root_cause"]
    duration = incident["duration_min"]

    # Symptom description from alert
    if alert_info:
        symptom = f"Alert fired for {alert_info['metric']} (value: {alert_info['value']}, threshold: {alert_info['threshold']})."
    else:
        symptom = f"Service degradation and elevated error rates reported in {service_name}."

    # Deployment context
    if recent_deploy:
        deployment_desc = f"Deployment '{recent_deploy['summary']}' was pushed (config_change={recent_deploy['config_change']})."
    else:
        deployment_desc = "No immediate deployment preceded this incident (traffic/infrastructure anomaly)."

    # Extract failed and worked fixes
    failed_fixes = [f["action"] for f in fix_attempts if f["outcome"] == "failed"]
    worked_fixes = [f["action"] for f in fix_attempts if f["outcome"] == "worked"]
    partial_fixes = [f["action"] for f in fix_attempts if f["outcome"] == "partial"]

    failed_fix_text = "; ".join(failed_fixes) if failed_fixes else "None recorded"
    worked_fix_text = "; ".join(worked_fixes) if worked_fixes else "Mitigated via automated rollback"
    
    sections = [
        f"[{code}]",
        f"[{service_name}]",
        f"[family: {family}]",
        "",
        "Symptom:",
        symptom,
        "",
        "Deployment:",
        deployment_desc,
        "",
        "Failed fix:",
        failed_fix_text,
        "",
        "Outcome:",
        "FAILED." if failed_fixes else "N/A",
        "",
        "Root cause:",
        root_cause,
        "",
        "Successful fix:",
        worked_fix_text,
        "",
        "Outcome:",
        "WORKED.",
        "",
        "Resolution time:",
        f"{duration} minutes.",
    ]
    if partial_fixes:
        sections.insert(12, f"Partial fix:\n{'; '.join(partial_fixes)}\nOutcome:\nPARTIAL.\n")

    return "\n".join(sections)


def seed_hindsight(
    dry_run: bool = False,
    bank_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extracts historical incidents (1-70) and seeds Hindsight Cloud.
    Guarantees replay incidents (71-110) are held out.
    """
    bank_id = bank_id or os.getenv("HINDSIGHT_BANK_ID", "kartly-sre")
    api_key = api_key or os.getenv("HINDSIGHT_API_KEY", "")
    base_url = base_url or os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io")

    logger.info(f"Preparing Hindsight memory seeding for bank: '{bank_id}'")
    dataset = build_complete_dataset(seed=42)

    # STRICT CHECK: Only take historical incidents 1 to 70
    historical_incidents = [
        inc for inc in dataset["incidents"]
        if inc["id"] <= 70 and int(inc["code"].split("-")[1]) <= 70
    ]
    assert len(historical_incidents) == 70, f"Expected 70 historical incidents, found {len(historical_incidents)}"

    # Service map
    service_map = {s["id"]: s["name"] for s in dataset["services"]}
    alert_map = {a["id"]: a for a in dataset["alerts"]}

    # Fix attempts indexed by incident_id
    fixes_by_incident: Dict[int, List[Dict[str, Any]]] = {}
    for fix in dataset["fix_attempts"]:
        fixes_by_incident.setdefault(fix["incident_id"], []).append(fix)

    # Deploys indexed by service_id
    deploys_by_service: Dict[int, List[Dict[str, Any]]] = {}
    for dep in dataset["deploys"]:
        deploys_by_service.setdefault(dep["service_id"], []).append(dep)

    # Sort historical incidents chronologically
    historical_incidents.sort(key=lambda x: x["opened_at"])

    # Prepare batch memory units
    memories_to_retain: List[Dict[str, Any]] = []

    for inc in historical_incidents:
        inc_id = inc["id"]
        alert = alert_map.get(inc.get("alert_id"))
        service_id = alert["service_id"] if alert else 1
        service_name = service_map.get(service_id, "checkout-api")

        # Find recent deployment prior to incident
        svc_deploys = deploys_by_service.get(service_id, [])
        prior_deploys = [d for d in svc_deploys if d["deployed_at"] <= inc["opened_at"]]
        recent_deploy = prior_deploys[-1] if prior_deploys else None

        fixes = fixes_by_incident.get(inc_id, [])

        memory_content = format_incident_memory(
            incident=inc,
            service_name=service_name,
            alert_info=alert,
            recent_deploy=recent_deploy,
            fix_attempts=fixes,
        )

        tags = [
            inc["code"],
            service_name,
            f"family:{inc['root_cause_family']}",
            f"severity:{inc['severity']}",
            "historical_incident",
        ]

        memories_to_retain.append({
            "document_id": f"kartly-{inc['code'].lower()}",
            "content": memory_content,
            "timestamp": inc["opened_at"],
            "context": f"Kartly Incident Postmortem - {inc['code']}",
            "tags": tags,
            "metadata": {
                "incident_code": inc["code"],
                "service": service_name,
                "root_cause_family": inc["root_cause_family"],
                "duration_min": str(inc["duration_min"]),
            },
        })

    is_live = bool(api_key and api_key != "your_hindsight_api_key_here" and not dry_run)
    logger.info(f"Target dataset: {len(memories_to_retain)} memories. Mode: {'LIVE HINDSIGHT CLOUD' if is_live else 'MOCK / DRY-RUN'}")

    retained_count = 0
    start_time = time.time()

    if is_live:
        try:
            from hindsight_client import Hindsight
            client = Hindsight(base_url=base_url, api_key=api_key)

            # Ensure bank exists
            try:
                client.create_bank(
                    bank_id=bank_id,
                    name="Kartly SRE Operational Memory",
                    mission="Store and recall recurring incident failure patterns, root causes, failed fixes, and successful remediations for Kartly microservices.",
                )
                logger.info(f"Created or verified bank: {bank_id}")
            except Exception as bank_err:
                logger.info(f"Bank check notice: {bank_err}")

            # Retain sequentially preserving timestamps and document_id for idempotency
            for item in memories_to_retain:
                client.retain(
                    bank_id=bank_id,
                    document_id=item["document_id"],
                    content=item["content"],
                    timestamp=item["timestamp"],
                    context=item["context"],
                    tags=item["tags"],
                    metadata=item["metadata"],
                )
                retained_count += 1
                if retained_count % 10 == 0:
                    logger.info(f"Retained {retained_count}/{len(memories_to_retain)} memories in Hindsight...")

        except Exception as e:
            logger.error(f"Failed live retention in Hindsight: {e}")
            raise
    else:
        # Verified mock retention
        logger.info("[Dry Run] Simulating Hindsight retention for historical incidents...")
        for item in memories_to_retain:
            # Validate payload schema
            assert len(item["content"]) > 50, "Memory content too short"
            assert isinstance(item["timestamp"], datetime), "Timestamp must be datetime"
            assert "historical_incident" in item["tags"], "Tags missing"
            assert not any(int(tag.split("-")[1]) > 70 for tag in item["tags"] if tag.startswith("INC-")), "LEAK DETECTED!"
            retained_count += 1

    elapsed = time.time() - start_time
    logger.info(f"Hindsight retention completed: {retained_count} memories processed in {elapsed:.2f}s.")

    return {
        "bank_id": bank_id,
        "mode": "live" if is_live else "dry_run",
        "historical_retained": retained_count,
        "replay_held_out": len(dataset["held_out_incidents"]),
        "elapsed_seconds": round(elapsed, 3),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed historical incident memory into Hindsight")
    parser.add_argument("--dry-run", action="store_true", help="Simulate seeding without making API calls")
    args = parser.parse_args()

    res = seed_hindsight(dry_run=args.dry_run)
    print("Hindsight Seeding Summary:", res)
