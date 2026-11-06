"""
RecallOps - Master Dataset Builder & Partition Orchestrator
Member 3: Database & Data Engineering

Orchestrates deterministic synthetic data generation for Kartly SRE:
- 6 services
- 8 engineers
- 400 deployments
- 110 incidents (INC-0001 through INC-0110)
- Partitions into:
    * Historical Memory Dataset: INC-0001 to INC-0070 (70 incidents)
    * Held-Out Replay Dataset:   INC-0071 to INC-0110 (40 incidents)
- Exports clean JSON and CSV snapshots to data/replay/
"""

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from data.generators.deploy_generator import generate_deployments
from data.generators.incident_generator import generate_incidents_and_related_data
from data.generators.kartly_company import ENGINEERS_DATA, SERVICES_DATA


def datetime_serializer(obj: Any) -> Any:
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def build_complete_dataset(
    seed: int = 42,
    num_deploys: int = 400,
    num_incidents: int = 110,
) -> Dict[str, Any]:
    """
    Build the complete Kartly operational dataset deterministically.
    """
    # 6-month historical window up to current date
    end_time = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    start_time = end_time - timedelta(days=180)

    # 1. Services & Engineers
    engineers = [dict(e) for e in ENGINEERS_DATA]
    services = [dict(s) for s in SERVICES_DATA]

    # 2. Deployments (~400)
    deployments = generate_deployments(
        services=services,
        engineers=engineers,
        start_time=start_time,
        end_time=end_time,
        target_count=num_deploys,
        seed=seed,
    )

    # 3. Alerts, Incidents, Logs, Fix Attempts (110 incidents)
    alerts, incidents, log_lines, fix_attempts = generate_incidents_and_related_data(
        services=services,
        engineers=engineers,
        deployments=deployments,
        start_time=start_time,
        end_time=end_time,
        total_incidents=num_incidents,
        seed=seed,
    )

    # 4. Split datasets: Historical (1-70) vs. Held-Out Replay (71-110)
    historical_incidents = [inc for inc in incidents if inc["id"] <= 70]
    held_out_incidents = [inc for inc in incidents if inc["id"] > 70]

    historical_ids = set(inc["id"] for inc in historical_incidents)
    held_out_ids = set(inc["id"] for inc in held_out_incidents)

    return {
        "engineers": engineers,
        "services": services,
        "deploys": deployments,
        "alerts": alerts,
        "incidents": incidents,
        "log_lines": log_lines,
        "fix_attempts": fix_attempts,
        "historical_incidents": historical_incidents,
        "held_out_incidents": held_out_incidents,
        "historical_ids": historical_ids,
        "held_out_ids": held_out_ids,
    }


def export_replay_and_sample_datasets(base_dir: str = ".") -> None:
    """
    Generate and export JSON and CSV artifacts for both replay partitions and samples.
    """
    dataset = build_complete_dataset()

    history_dir = os.path.join(base_dir, "data", "replay", "history")
    held_out_dir = os.path.join(base_dir, "data", "replay", "held_out")
    samples_dir = os.path.join(base_dir, "data", "samples")

    os.makedirs(history_dir, exist_ok=True)
    os.makedirs(held_out_dir, exist_ok=True)
    os.makedirs(samples_dir, exist_ok=True)

    # Helper to serialize records
    def save_json(path: str, data: Any):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=datetime_serializer)

    def save_csv(path: str, records: List[Dict[str, Any]]):
        if not records:
            return
        keys = list(records[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in records:
                row = dict(r)
                for k, v in row.items():
                    if isinstance(v, (datetime,)):
                        row[k] = v.isoformat()
                    elif isinstance(v, (dict, list)):
                        row[k] = json.dumps(v)
                writer.writerow(row)

    # 1. Historical dataset exports (INC-0001 to INC-0070)
    save_json(os.path.join(history_dir, "incidents.json"), dataset["historical_incidents"])
    save_csv(os.path.join(history_dir, "incidents.csv"), dataset["historical_incidents"])

    # 2. Held-Out Replay dataset exports (INC-0071 to INC-0110)
    save_json(os.path.join(held_out_dir, "incidents.json"), dataset["held_out_incidents"])
    save_csv(os.path.join(held_out_dir, "incidents.csv"), dataset["held_out_incidents"])

    # 3. Sample exports for quick inspection by Backend & Frontend
    sample_data = {
        "services": dataset["services"][:3],
        "engineers": dataset["engineers"][:4],
        "sample_deploys": dataset["deploys"][:5],
        "sample_incidents": dataset["incidents"][:3],
        "sample_logs": dataset["log_lines"][:10],
        "sample_fixes": dataset["fix_attempts"][:5],
    }
    save_json(os.path.join(samples_dir, "kartly_sample.json"), sample_data)


if __name__ == "__main__":
    export_replay_and_sample_datasets()
    print("Kartly dataset generation and export completed successfully.")
