"""
RecallOps - PostgreSQL High-Performance Database Seeder
Member 3: Database & Data Engineering

Loads the complete deterministic Kartly operational dataset into PostgreSQL:
- 8 engineers
- 6 services
- ~400 deployments
- 110 incidents (70 historical, 40 replay)
- ~3,500+ realistic logs (20-50 per incident)
- Fix attempts with authentic outcomes
"""

import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import get_engine, get_session_factory, init_db
from database.models import (
    Alert,
    Deploy,
    Engineer,
    FixAttempt,
    Incident,
    LogLine,
    Service,
)
from data.generators.dataset_builder import build_complete_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_postgres")


def seed_postgres(engine=None, reset_first: bool = True) -> dict:
    """
    Seed PostgreSQL with the complete Kartly dataset.
    Returns summary statistics of inserted rows.
    """
    start_time = time.time()
    eng = engine or get_engine()
    
    if reset_first:
        logger.info("Initializing fresh database schema...")
        init_db(engine=eng, drop_all=True)

    SessionFactory = get_session_factory(eng)
    session = SessionFactory()

    try:
        # Check if database already has records (Duplicate Prevention)
        existing_incidents = session.query(Incident).count()
        if existing_incidents > 0 and not reset_first:
            logger.warning(
                f"Database already contains {existing_incidents} incidents. "
                "Skipping seeding to prevent duplicate records."
            )
            return {
                "status": "skipped",
                "reason": "already_seeded",
                "incidents": existing_incidents,
                "elapsed_seconds": round(time.time() - start_time, 3),
            }

        logger.info("Generating synthetic dataset (seed=42)...")
        dataset = build_complete_dataset(seed=42)
        # 1. Engineers
        logger.info(f"Seeding {len(dataset['engineers'])} engineers...")
        for e in dataset["engineers"]:
            eng_obj = Engineer(
                id=e["id"],
                name=e["name"],
                team=e["team"],
                slack_handle=e["slack_handle"],
            )
            session.add(eng_obj)
        session.flush()

        # 2. Services
        logger.info(f"Seeding {len(dataset['services'])} services...")
        for s in dataset["services"]:
            svc_obj = Service(
                id=s["id"],
                name=s["name"],
                team=s["team"],
                owner_id=s["owner_id"],
                tier=s["tier"],
            )
            session.add(svc_obj)
        session.flush()

        # 3. Deployments
        logger.info(f"Seeding {len(dataset['deploys'])} deployments...")
        deploy_objs = [
            Deploy(
                id=d["id"],
                service_id=d["service_id"],
                author_id=d["author_id"],
                deployed_at=d["deployed_at"],
                summary=d["summary"],
                config_change=d["config_change"],
                diff_note=d["diff_note"],
            )
            for d in dataset["deploys"]
        ]
        session.bulk_save_objects(deploy_objs)
        session.flush()

        # 4. Alerts
        logger.info(f"Seeding {len(dataset['alerts'])} alerts...")
        alert_objs = [
            Alert(
                id=a["id"],
                service_id=a["service_id"],
                metric=a["metric"],
                threshold=a["threshold"],
                value=a["value"],
                fired_at=a["fired_at"],
                payload=a["payload"],
            )
            for a in dataset["alerts"]
        ]
        session.bulk_save_objects(alert_objs)
        session.flush()

        # 5. Incidents
        logger.info(f"Seeding {len(dataset['incidents'])} incidents...")
        incident_objs = [
            Incident(
                id=i["id"],
                code=i["code"],
                alert_id=i["alert_id"],
                severity=i["severity"],
                status=i["status"],
                opened_at=i["opened_at"],
                resolved_at=i["resolved_at"],
                root_cause=i["root_cause"],
                root_cause_family=i["root_cause_family"],
                duration_min=i["duration_min"],
            )
            for i in dataset["incidents"]
        ]
        session.bulk_save_objects(incident_objs)
        session.flush()

        # 6. Log Lines
        logger.info(f"Seeding {len(dataset['log_lines'])} operational log lines...")
        log_objs = [
            LogLine(
                id=l["id"],
                incident_id=l["incident_id"],
                ts=l["ts"],
                level=l["level"],
                source=l["source"],
                message=l["message"],
            )
            for l in dataset["log_lines"]
        ]
        session.bulk_save_objects(log_objs)
        session.flush()

        # 7. Fix Attempts
        logger.info(f"Seeding {len(dataset['fix_attempts'])} fix attempts...")
        fix_objs = [
            FixAttempt(
                id=f["id"],
                incident_id=f["incident_id"],
                action=f["action"],
                outcome=f["outcome"],
                by_engineer=f["by_engineer"],
                at=f["at"],
            )
            for f in dataset["fix_attempts"]
        ]
        session.bulk_save_objects(fix_objs)
        session.commit()

        elapsed = time.time() - start_time
        logger.info(f"PostgreSQL seeding completed successfully in {elapsed:.2f} seconds.")

        return {
            "engineers": len(dataset["engineers"]),
            "services": len(dataset["services"]),
            "deploys": len(dataset["deploys"]),
            "alerts": len(dataset["alerts"]),
            "incidents": len(dataset["incidents"]),
            "log_lines": len(dataset["log_lines"]),
            "fix_attempts": len(dataset["fix_attempts"]),
            "elapsed_seconds": round(elapsed, 3),
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error seeding database: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    stats = seed_postgres()
    print("Seed Summary:", stats)
