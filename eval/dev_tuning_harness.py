"""
RecallOps Dev Incident Tuning Harness (Phase 2)
Author: Member 4 (AI/ML & Model)
Phase: Phase 2: Core Loop (H8–H16)

Evaluates the RecallPipeline against a suite of 10 realistic development incidents:
1. HikariCP Connection Pool Exhaustion (payments-db)
2. Redis MaxMemory Eviction & OOM (cart-service)
3. Unsynchronized Feature Flag Toggle (checkout-api)
4. Expired Ingress TLS Certificate (ingress-gateway)
5. Kafka Consumer Group Rebalance Storm (order-worker)
6. JVM Heap Memory Leak in Batch Cache (inventory-service)
7. CoreDNS Search Domain Resolution Loop (payments-db / stripe-gateway)
8. Unindexed SQL Migration Table Lock (auth-service)
9. Ingress Nginx Worker Connection Starvation (ingress-gateway)
10. IAM S3 PutObject Permission Revocation (billing-service)

Measures:
- Top-1 Accuracy: True root cause is the #1 ranked hypothesis.
- Top-3 Accuracy: True root cause appears in the Top-3 ranked hypotheses (Target >= 80%).
- Failed Fix Warning Detection Rate: Known anti-patterns flagged in `failed_fixes_warnings`.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
from pydantic import BaseModel, Field

# Ensure root repository is in sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from eval.recall_pipeline import RecallPipeline, TripartiteRecallResult
from eval.memory_templates import FixOutcome


# ==============================================================================
# 1. SYNTHETIC HISTORICAL MEMORY CORPUS (Hindsight Database)
# ==============================================================================

HISTORICAL_MEMORY_CORPUS: List[Dict[str, Any]] = [
    # Match for Dev Incident 1: HikariCP pool leak
    {
        "incident_id": "INC-1987",
        "service_name": "payments-db",
        "symptom": "HTTP 500 timeout storm on /checkout/pay HikariCP-1 connection is not available",
        "root_cause": "HikariCP connection pool exhaustion due to leaked connection in unclosed ResultSet",
        "successful_fix": "Applied hotfix closing ResultSet in try-with-resources and raised max-pool-size to 25",
        "failed_actions": ["restart PostgreSQL container", "reboot database host"],
        "is_negative_memory": True,
        "timestamp": "2026-09-14T10:15:00Z",
    },
    # Match for Dev Incident 2: Redis eviction & OOM
    {
        "incident_id": "INC-1842",
        "service_name": "cart-service",
        "symptom": "OOMKilled pod restarts on redis-cart cluster, session drops and memory peak",
        "root_cause": "Redis maxmemory exhaustion triggering volatile-lru eviction storm on cart sessions",
        "successful_fix": "Configured cart TTL to 48 hours and scaled redis-cart memory limit from 4Gi to 8Gi",
        "failed_actions": ["increase replica count of cart-service", "restart cart pods"],
        "is_negative_memory": True,
        "timestamp": "2026-08-20T14:30:00Z",
    },
    # Match for Dev Incident 3: Feature flag toggle
    {
        "incident_id": "INC-2041",
        "service_name": "checkout-api",
        "symptom": "NullPointerException in CheckoutFlowController.processOrder post flag activation",
        "root_cause": "Feature flag enable-one-click-checkout-v2 enabled before downstream payment v2 API deployment",
        "successful_fix": "Disabled flag enable-one-click-checkout-v2 via LaunchDarkly console",
        "failed_actions": ["rollback checkout-api deployment", "restart checkout pods"],
        "is_negative_memory": True,
        "timestamp": "2026-10-02T11:00:00Z",
    },
    # Match for Dev Incident 4: Expired TLS cert
    {
        "incident_id": "INC-1720",
        "service_name": "ingress-gateway",
        "symptom": "Client SSL handshake failures certificate has expired on api.kartly.com",
        "root_cause": "Expired TLS certificate on ingress secret due to cert-manager ACME solver eviction",
        "successful_fix": "Manually re-triggered cert-manager challenge and updated secret kartly-tls-cert",
        "failed_actions": ["restart Nginx ingress controller", "flush DNS cache"],
        "is_negative_memory": True,
        "timestamp": "2026-07-15T08:20:00Z",
    },
    # Match for Dev Incident 5: Kafka consumer rebalance
    {
        "incident_id": "INC-1930",
        "service_name": "order-worker",
        "symptom": "Consumer lag skyrocketing on order-created topic, partitions stuck in continuous rebalance",
        "root_cause": "Kafka consumer group rebalance storm caused by poll timeout during slow batch processing",
        "successful_fix": "Increased max.poll.interval.ms to 300000 and reduced max.poll.records from 500 to 50",
        "failed_actions": ["kill consumer pods", "delete consumer group"],
        "is_negative_memory": True,
        "timestamp": "2026-09-02T16:45:00Z",
    },
    # Match for Dev Incident 6: JVM Heap Memory Leak
    {
        "incident_id": "INC-2015",
        "service_name": "inventory-service",
        "symptom": "java.lang.OutOfMemoryError Java heap space during flash sale batch sync",
        "root_cause": "Unbounded static cache accumulation in JVM heap due to missing cache expiration policy",
        "successful_fix": "Replaced static ConcurrentHashMap with Caffeine cache with 10k entry limit and 1h TTL",
        "failed_actions": ["increase pod memory limit from 2Gi to 4Gi", "increase replica count"],
        "is_negative_memory": True,
        "timestamp": "2026-09-28T19:10:00Z",
    },
    # Match for Dev Incident 7: CoreDNS search domain loop
    {
        "incident_id": "INC-1680",
        "service_name": "payments-db",
        "symptom": "i/o timeout resolving api.stripe.com 504 Gateway Timeouts on payment capture",
        "root_cause": "CoreDNS search domain loops causing 5-second DNS resolution latency for external FQDNs",
        "successful_fix": "Appended trailing dot api.stripe.com. and configured ndots:2 in pod dnsConfig",
        "failed_actions": ["restart payment-gateway pods", "restart payment db"],
        "is_negative_memory": True,
        "timestamp": "2026-06-11T13:00:00Z",
    },
    # Match for Dev Incident 8: Table lock during migration
    {
        "incident_id": "INC-1888",
        "service_name": "auth-service",
        "symptom": "All authentication requests hanging, PostgreSQL pg_stat_activity shows exclusive table lock",
        "root_cause": "Exclusive table lock on users table during synchronous foreign key validation migration",
        "successful_fix": "Cancelled blocking DDL query and added FK with NOT VALID followed by VALIDATE CONSTRAINT",
        "failed_actions": ["terminate user-facing backend connections", "restart auth pods"],
        "is_negative_memory": True,
        "timestamp": "2026-08-30T22:15:00Z",
    },
    # Match for Dev Incident 9: Nginx worker connection starvation
    {
        "incident_id": "INC-1955",
        "service_name": "ingress-gateway",
        "symptom": "504 Gateway Timeout across all public routes, ingress worker connections maxed at 1024",
        "root_cause": "Worker connection starvation caused by excessive keepalive_timeout and slow upstream responses",
        "successful_fix": "Increased worker_connections to 16384 and lowered keepalive_timeout to 65s",
        "failed_actions": ["scale up upstream service pods", "restart backend microservices"],
        "is_negative_memory": True,
        "timestamp": "2026-09-10T17:05:00Z",
    },
    # Match for Dev Incident 10: IAM S3 permission revoked
    {
        "incident_id": "INC-2088",
        "service_name": "billing-service",
        "symptom": "AccessDenied Request has expired or Forbidden on invoice PDF generation and s3 upload",
        "root_cause": "IAM policy update pruned s3:PutObject on kartly-invoices bucket for billing role",
        "successful_fix": "Re-attached AmazonS3InvoiceBucketPolicy to billing-service-iam-role",
        "failed_actions": ["re-deploy billing-service", "restart billing worker"],
        "is_negative_memory": True,
        "timestamp": "2026-10-18T12:00:00Z",
    },
    # Distractors (competing noise to test ranking robustness)
    {
        "incident_id": "INC-1500",
        "service_name": "payments-db",
        "symptom": "Slow disk I/O on EBS gp2 volume during nightly backup",
        "root_cause": "EBS burst balance depletion during pg_dump",
        "successful_fix": "Upgraded EBS volume to gp3 with 3000 baseline IOPS",
        "failed_actions": [],
        "is_negative_memory": False,
        "timestamp": "2026-05-01T04:00:00Z",
    },
    {
        "incident_id": "INC-1610",
        "service_name": "checkout-api",
        "symptom": "HTTP 429 Too Many Requests rate limit triggered by mobile client retry loop",
        "root_cause": "Aggressive mobile app retry without exponential backoff",
        "successful_fix": "Configured envoy rate limit token bucket filter",
        "failed_actions": [],
        "is_negative_memory": False,
        "timestamp": "2026-05-20T10:00:00Z",
    },
]


# ==============================================================================
# 2. 10 REALISTIC DEVELOPMENT INCIDENTS BENCHMARK
# ==============================================================================

class DevIncidentBenchmark(BaseModel):
    incident_id: str
    service_name: str
    symptom: str
    recent_deploy_diff: str
    ground_truth_root_cause_keyword: str
    ground_truth_incident_id: str
    known_failed_fix_keyword: str


DEV_INCIDENTS_SUITE: List[DevIncidentBenchmark] = [
    DevIncidentBenchmark(
        incident_id="DEV-INC-101",
        service_name="payments-db",
        symptom="500 timeout storm on /checkout/pay HikariCP connection pool exhausted",
        recent_deploy_diff="Bumped max-pool-size to 10 but increased connection timeout to 60s in db-config.yaml",
        ground_truth_root_cause_keyword="HikariCP",
        ground_truth_incident_id="INC-1987",
        known_failed_fix_keyword="restart",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-102",
        service_name="cart-service",
        symptom="OOMKilled pod restarts on redis-cart cluster, session drops and memory peak",
        recent_deploy_diff="Cart session TTL increased from 24h to 30 days without memory limit expansion",
        ground_truth_root_cause_keyword="Redis",
        ground_truth_incident_id="INC-1842",
        known_failed_fix_keyword="replica",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-103",
        service_name="checkout-api",
        symptom="NullPointerException in CheckoutFlowController.processOrder post flag activation",
        recent_deploy_diff="Toggled flag enable-one-click-checkout-v2 to 100% rollout in config",
        ground_truth_root_cause_keyword="feature flag",
        ground_truth_incident_id="INC-2041",
        known_failed_fix_keyword="rollback",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-104",
        service_name="ingress-gateway",
        symptom="Client SSL handshake failures certificate has expired on api.kartly.com",
        recent_deploy_diff="No recent code deploy; cert-manager pod evicted",
        ground_truth_root_cause_keyword="TLS certificate",
        ground_truth_incident_id="INC-1720",
        known_failed_fix_keyword="restart",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-105",
        service_name="order-worker",
        symptom="Consumer lag skyrocketing on order-created topic, partitions stuck in continuous rebalance",
        recent_deploy_diff="max.poll.interval.ms set to 5000ms with slow external inventory call",
        ground_truth_root_cause_keyword="Kafka",
        ground_truth_incident_id="INC-1930",
        known_failed_fix_keyword="kill",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-106",
        service_name="inventory-service",
        symptom="java.lang.OutOfMemoryError Java heap space during flash sale batch sync",
        recent_deploy_diff="New batch inventory cache using static ConcurrentHashMap without eviction",
        ground_truth_root_cause_keyword="cache",
        ground_truth_incident_id="INC-2015",
        known_failed_fix_keyword="pod memory limit",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-107",
        service_name="payments-db",
        symptom="i/o timeout resolving api.stripe.com 504 Gateway Timeouts on payment capture",
        recent_deploy_diff="CoreDNS configmap modified with custom search domain",
        ground_truth_root_cause_keyword="DNS",
        ground_truth_incident_id="INC-1680",
        known_failed_fix_keyword="restart",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-108",
        service_name="auth-service",
        symptom="All authentication requests hanging, PostgreSQL pg_stat_activity shows exclusive table lock",
        recent_deploy_diff="Flyway migration adding foreign key constraint without NOT VALID",
        ground_truth_root_cause_keyword="table lock",
        ground_truth_incident_id="INC-1888",
        known_failed_fix_keyword="terminate",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-109",
        service_name="ingress-gateway",
        symptom="504 Gateway Timeout across all public routes, ingress worker connections maxed at 1024",
        recent_deploy_diff="worker-connections set to 1024 with keepalive_timeout 300s",
        ground_truth_root_cause_keyword="Worker connection",
        ground_truth_incident_id="INC-1955",
        known_failed_fix_keyword="upstream",
    ),
    DevIncidentBenchmark(
        incident_id="DEV-INC-110",
        service_name="billing-service",
        symptom="AccessDenied Request has expired or Forbidden on invoice PDF generation and s3 upload",
        recent_deploy_diff="AWS IAM role policy updated by security audit script",
        ground_truth_root_cause_keyword="IAM policy",
        ground_truth_incident_id="INC-2088",
        known_failed_fix_keyword="re-deploy",
    ),
]


# ==============================================================================
# 3. TUNING EVALUATOR
# ==============================================================================

class TuningEvaluationReport(BaseModel):
    total_incidents: int
    top_1_hits: int
    top_3_hits: int
    failed_fix_warning_hits: int
    top_1_accuracy_pct: float
    top_3_accuracy_pct: float
    warning_detection_pct: float
    benchmark_passed: bool
    incident_details: List[Dict[str, Any]]


def run_tuning_suite(
    pipeline: Optional[RecallPipeline] = None,
    engineer_id: str = "priya",
    verbose: bool = True,
) -> TuningEvaluationReport:
    """
    Executes the recall pipeline across all 10 synthetic dev incidents,
    verifying top-1, top-3 accuracy, and negative memory warnings.
    """
    if pipeline is None:
        pipeline = RecallPipeline(memory_store=HISTORICAL_MEMORY_CORPUS)

    top_1_hits = 0
    top_3_hits = 0
    failed_warning_hits = 0
    details: List[Dict[str, Any]] = []

    if verbose:
        print("=" * 80)
        print("RECALLOPS PHASE 2: DEV INCIDENT TUNING HARNESS (10 INCIDENTS)")
        print("=" * 80)
        print(f"{'Incident ID':<12} | {'Service':<17} | {'Top Rank':<10} | {'Score':<6} | {'Top-3':<5} | {'Warning':<7}")
        print("-" * 80)

    for item in DEV_INCIDENTS_SUITE:
        result: TripartiteRecallResult = pipeline.execute_tripartite_recall(
            service_name=item.service_name,
            symptom=item.symptom,
            recent_deploy_diff=item.recent_deploy_diff,
            engineer_id=engineer_id,
        )

        ranked = result.ranked_hypotheses
        top_ids = [h.incident_id.upper() for h in ranked[:3]]

        is_top_1 = (len(top_ids) > 0 and top_ids[0] == item.ground_truth_incident_id.upper())
        is_top_3 = item.ground_truth_incident_id.upper() in top_ids

        if is_top_1:
            top_1_hits += 1
        if is_top_3:
            top_3_hits += 1

        # Check if known failed action was flagged in failed_fixes_warnings
        has_warning = False
        kw = item.known_failed_fix_keyword.lower()
        for w in result.failed_fixes_warnings:
            if kw in w.lower() or item.ground_truth_incident_id in w:
                has_warning = True
                break
        if has_warning:
            failed_warning_hits += 1

        top_score = ranked[0].confidence_score if ranked else 0.0
        top_rank_id = ranked[0].incident_id if ranked else "NONE"

        details.append(
            {
                "dev_incident_id": item.incident_id,
                "service_name": item.service_name,
                "expected_incident_id": item.ground_truth_incident_id,
                "top_ranked_id": top_rank_id,
                "top_score": top_score,
                "top_3_ids": top_ids,
                "is_top_1": is_top_1,
                "is_top_3": is_top_3,
                "warning_detected": has_warning,
            }
        )

        if verbose:
            top_3_str = "YES" if is_top_3 else "NO"
            warn_str = "YES" if has_warning else "NO"
            print(f"{item.incident_id:<12} | {item.service_name:<17} | {top_rank_id:<10} | {top_score:<6.2f} | {top_3_str:<5} | {warn_str:<7}")

    total = len(DEV_INCIDENTS_SUITE)
    top_1_pct = round((top_1_hits / total) * 100.0, 1)
    top_3_pct = round((top_3_hits / total) * 100.0, 1)
    warn_pct = round((failed_warning_hits / total) * 100.0, 1)
    passed = top_3_pct >= 80.0

    if verbose:
        print("=" * 80)
        print("TUNING SUMMARY")
        print("=" * 80)
        print(f"Top-1 Accuracy          : {top_1_pct}% ({top_1_hits}/{total})")
        print(f"Top-3 Accuracy          : {top_3_pct}% ({top_3_hits}/{total})  [Target >= 80%]")
        print(f"Failed Fix Warning Rate : {warn_pct}% ({failed_warning_hits}/{total})")
        print(f"Tuning Benchmark Status : {'PASSED [OK]' if passed else 'FAILED'}")
        print("=" * 80)

    return TuningEvaluationReport(
        total_incidents=total,
        top_1_hits=top_1_hits,
        top_3_hits=top_3_hits,
        failed_fix_warning_hits=failed_warning_hits,
        top_1_accuracy_pct=top_1_pct,
        top_3_accuracy_pct=top_3_pct,
        warning_detection_pct=warn_pct,
        benchmark_passed=passed,
        incident_details=details,
    )


if __name__ == "__main__":
    report = run_tuning_suite(verbose=True)
    if not report.benchmark_passed:
        print("[FAIL] Benchmark failed accuracy requirement!")
        sys.exit(1)
    print("[SUCCESS] Dev Incident Tuning Benchmark successfully met target threshold (>=80%).")
    sys.exit(0)
