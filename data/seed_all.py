"""
RecallOps - Master Seed & Reset Orchestrator
Member 3: Database & Data Engineering

Runs complete end-to-end initialization:
1. Resets database schema.
2. Seeds PostgreSQL with Kartly operational dataset.
3. Exports replay dataset files (historical & held-out).
4. Seeds Hindsight memory bank (live or dry-run).
5. Runs full data validation.
Reports total execution time (Target: < 60 seconds).
"""

import argparse
import logging
import os
import sys
import time

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data.generators.dataset_builder import export_replay_and_sample_datasets
from data.reset_database import reset_database
from data.seed_hindsight import seed_hindsight
from data.seed_postgres import seed_postgres
from data.validate_data import validate_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_all")


def run_full_pipeline(dry_run: bool = False) -> bool:
    pipeline_start = time.time()
    print("\n" + "=" * 70)
    print("RECALLOPS - FULL SEED & INITIALIZATION PIPELINE")
    print("=" * 70)

    # Step 1: Database Reset & Schema Creation
    print("\n[STEP 1/5] Resetting PostgreSQL schema...")
    reset_res = reset_database(reseed=False)
    print(f"  -> Schema recreated in {reset_res['total_elapsed_seconds']:.2f}s")

    # Step 2: Seed PostgreSQL
    print("\n[STEP 2/5] Seeding PostgreSQL with 6 services, 8 engineers, 400 deploys, 110 incidents...")
    seed_stats = seed_postgres(reset_first=False)
    print(f"  -> Seeded {seed_stats['incidents']} incidents and {seed_stats['log_lines']} logs in {seed_stats['elapsed_seconds']:.2f}s")

    # Step 3: Export Replay Datasets
    print("\n[STEP 3/5] Partitioning & exporting replay datasets...")
    export_start = time.time()
    export_replay_and_sample_datasets()
    print(f"  -> Exported replay files to data/replay/ in {time.time() - export_start:.2f}s")

    # Step 4: Seed Hindsight Memory Bank (Historical 1-70 only)
    print("\n[STEP 4/5] Seeding Hindsight memory bank 'kartly-sre'...")
    hindsight_res = seed_hindsight(dry_run=dry_run)
    print(f"  -> {hindsight_res['historical_retained']} historical incidents retained (Mode: {hindsight_res['mode']}) in {hindsight_res['elapsed_seconds']:.2f}s")
    print(f"  -> STRICT CHECK: {hindsight_res['replay_held_out']} replay incidents remained held out.")

    # Step 5: Validate Data Integrity
    print("\n[STEP 5/5] Running data validation suite...")
    passed, errors, metrics = validate_dataset()
    if passed:
        print("  -> Data integrity verification: PASSED (10/10 checks)")
    else:
        print(f"  -> Data integrity verification: FAILED ({len(errors)} errors)")
        for e in errors[:5]:
            print(f"     * {e}")

    total_pipeline_time = time.time() - pipeline_start
    print("\n" + "=" * 70)
    print(f"PIPELINE COMPLETED IN {total_pipeline_time:.2f} SECONDS (Target: < 60s)")
    if total_pipeline_time < 60.0:
        print(">>> SUCCESS: RESET AND SEED TARGET CRITERIA MET. <<<")
    else:
        print(">>> WARNING: EXECUTION EXCEEDED 60 SECONDS. <<<")
    print("=" * 70 + "\n")

    return passed and total_pipeline_time < 60.0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run complete reset, seed, and validation pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run Hindsight seeding in dry-run mode")
    args = parser.parse_args()

    success = run_full_pipeline(dry_run=args.dry_run)
    sys.exit(0 if success else 1)
