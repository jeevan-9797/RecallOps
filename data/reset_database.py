"""
RecallOps - Safe Database Reset & Re-initialization
Member 3: Database & Data Engineering

Provides fast, safe reset of the database state in under 60 seconds:
1. Safely clears existing operational records.
2. Recreates approved schema tables.
3. Reseeds fresh deterministic data for Kartly.
4. Provides callable interface for Backend's protected /demo/reset endpoint.
"""

import logging
import os
import sys
import time
from typing import Any, Dict, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.connection import get_engine, init_db
from data.seed_postgres import seed_postgres

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reset_database")


def reset_database(engine=None, reseed: bool = True) -> Dict[str, Any]:
    """
    Reset and reseed database.
    Target execution time: < 60 seconds.
    """
    start_time = time.time()
    eng = engine or get_engine()

    logger.info("Starting safe database reset...")

    # Drop and recreate tables
    init_db(engine=eng, drop_all=True)

    seed_stats = {}
    if reseed:
        logger.info("Reseeding deterministic Kartly operational dataset...")
        seed_stats = seed_postgres(engine=eng, reset_first=False)

    total_elapsed = time.time() - start_time
    logger.info(f"Database reset and reseed completed in {total_elapsed:.2f} seconds.")

    return {
        "status": "success",
        "total_elapsed_seconds": round(total_elapsed, 3),
        "seed_stats": seed_stats,
    }


def reset_hindsight_bank(bank_id: Optional[str] = None, api_key: Optional[str] = None, base_url: Optional[str] = None) -> bool:
    """
    Cleans up the Hindsight bank if live API key is configured.
    """
    bank_id = bank_id or os.getenv("HINDSIGHT_BANK_ID", "kartly-sre")
    api_key = api_key or os.getenv("HINDSIGHT_API_KEY", "")
    base_url = base_url or os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io")

    if not api_key or api_key == "your_hindsight_api_key_here":
        logger.info("[Dry Run] Skipping remote Hindsight bank reset (no API key configured).")
        return True

    try:
        from hindsight_client import Hindsight
        client = Hindsight(base_url=base_url, api_key=api_key)
        logger.info(f"Deleting and recreating bank '{bank_id}' in Hindsight Cloud...")
        try:
            client.delete_bank(bank_id=bank_id)
        except Exception:
            pass  # Bank might not exist yet
            
        client.create_bank(
            bank_id=bank_id,
            name="Kartly SRE Operational Memory",
            mission="Store and recall recurring incident failure patterns, root causes, failed fixes, and successful remediations for Kartly microservices.",
        )
        logger.info("Hindsight bank reset successfully.")
        return True
    except Exception as e:
        logger.warning(f"Notice during Hindsight bank reset: {e}")
        return False


if __name__ == "__main__":
    result = reset_database()
    print("Reset Result:", result)
