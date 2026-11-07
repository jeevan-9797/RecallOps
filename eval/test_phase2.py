"""
Unit Tests for Phase 2: Multi-Bank Recall Pipeline, Ranking Engine, & Tuning Harness
Author: Member 4 (AI/ML & Model)
Phase: Phase 2: Core Loop (H8–H16)
"""

import pytest
from eval.recall_pipeline import (
    RecallPipeline,
    MemoryHit,
    StandingDirective,
    TripartiteRecallResult,
    compute_lexical_semantic_similarity,
)
from eval.dev_tuning_harness import (
    HISTORICAL_MEMORY_CORPUS,
    run_tuning_suite,
)


# ==============================================================================
# 1. TEXT SIMILARITY TESTS
# ==============================================================================

def test_compute_lexical_semantic_similarity():
    query = "payments-db connection pool exhausted timeout"
    candidate_match = "payments-db HikariCP connection pool exhausted post deploy"
    candidate_unrelated = "auth-service jwt token signature verification failed"

    sim_high = compute_lexical_semantic_similarity(query, candidate_match)
    sim_low = compute_lexical_semantic_similarity(query, candidate_unrelated)

    assert sim_high > 0.50
    assert sim_low < 0.20
    assert compute_lexical_semantic_similarity("", "test") == 0.0
    assert compute_lexical_semantic_similarity("test", "") == 0.0


# ==============================================================================
# 2. DEDUPLICATION & MERGING TESTS
# ==============================================================================

def test_deduplication_by_incident_id():
    pipeline = RecallPipeline()

    hit_1 = MemoryHit(
        incident_id="INC-1987",
        service_name="payments-db",
        root_cause="Connection pool leak",
        symptom="500 timeout",
        similarity_score=0.75,
        source_queries=["query_1_symptom"],
        failed_actions=["restart pods"],
    )
    hit_2 = MemoryHit(
        incident_id="INC-1987",
        service_name="payments-db",
        root_cause="Connection pool leak",
        symptom="Deploy bump pool size",
        successful_fix="Add index on orders.customer_id",
        similarity_score=0.88,  # Higher score
        source_queries=["query_2_deploy"],
        failed_actions=["reboot db host"],
    )
    hit_3 = MemoryHit(
        incident_id="INC-2041",
        service_name="checkout-api",
        root_cause="Feature flag error",
        symptom="NPE",
        similarity_score=0.60,
        source_queries=["query_1_symptom"],
    )

    deduped, warnings = pipeline._deduplicate_hits([hit_1, hit_2, hit_3])

    assert len(deduped) == 2
    inc_1987 = next(h for h in deduped if h.incident_id == "INC-1987")

    # Score kept the higher one (0.88)
    assert inc_1987.similarity_score == 0.88
    # Merged queries
    assert set(inc_1987.source_queries) == {"query_1_symptom", "query_2_deploy"}
    # Merged failed actions
    assert "restart pods" in inc_1987.failed_actions
    assert "reboot db host" in inc_1987.failed_actions
    # Successful fix preserved
    assert inc_1987.successful_fix == "Add index on orders.customer_id"

    # Warnings extracted
    assert any("restart pods" in w for w in warnings)
    assert any("reboot db host" in w for w in warnings)


# ==============================================================================
# 3. RANKING & NEGATIVE MEMORY PENALTY TESTS
# ==============================================================================

def test_ranking_outcome_penalty_on_pure_failed_fixes():
    pipeline = RecallPipeline(failure_penalty=0.50)

    # Candidate A: Successfully resolved incident
    good_hit = MemoryHit(
        incident_id="INC-1987",
        service_name="payments-db",
        root_cause="HikariCP connection pool exhausted",
        symptom="500 error",
        successful_fix="Increased pool size and fixed leak",
        similarity_score=0.85,
        is_negative_memory=False,
    )

    # Candidate B: Only an unsuccessful action attempt with NO working fix
    failed_hit = MemoryHit(
        incident_id="INC-9999",
        service_name="payments-db",
        root_cause="Failed attempt without resolution",
        symptom="500 error",
        successful_fix=None,
        similarity_score=0.85,
        is_negative_memory=True,  # Pure failure
    )

    ranked = pipeline.rank_hypotheses([good_hit, failed_hit], {"service_name": "payments-db", "symptom": "500 error"})

    assert len(ranked) == 2
    # Good hit must rank top
    assert ranked[0].incident_id == "INC-1987"
    assert ranked[1].incident_id == "INC-9999"
    # Failed hit confidence must be penalized
    assert ranked[1].confidence_score < ranked[0].confidence_score
    assert ranked[1].score_breakdown["penalty"] == 0.50


# ==============================================================================
# 4. STANDING DIRECTIVES (MENTAL MODELS) TESTS
# ==============================================================================

def test_standing_directives_trigger():
    pipeline = RecallPipeline()

    # payments-db connection issue should trigger RULE-PAY-01
    directives_pay = pipeline._check_standing_directives("payments-db", "connection pool saturated")
    assert len(directives_pay) >= 1
    assert any("RULE-PAY-01" in d for d in directives_pay)
    assert any("PgBouncer" in d for d in directives_pay)

    # ingress-gateway 504 timeouts should trigger RULE-INGR-03
    directives_ingr = pipeline._check_standing_directives("ingress-gateway", "504 gateway timeout storm")
    assert len(directives_ingr) >= 1
    assert any("RULE-INGR-03" in d for d in directives_ingr)

    # Unrelated service should not trigger payments or ingress rules
    directives_cart = pipeline._check_standing_directives("cart-service", "redis oom")
    assert not any("RULE-PAY-01" in d for d in directives_cart)


# ==============================================================================
# 5. ENGINEER PREFERENCE RESOLUTION TESTS
# ==============================================================================

def test_engineer_preference_resolution():
    pipeline = RecallPipeline()

    # Priya -> concise
    pref_priya = pipeline._resolve_engineer_preference("priya")
    assert pref_priya["style"] == "concise"
    assert "kubectl" in pref_priya["directive"]

    # Rahul -> detailed
    pref_rahul = pipeline._resolve_engineer_preference("rahul")
    assert pref_rahul["style"] == "detailed"
    assert "detailed" in pref_rahul["directive"]

    # Unknown engineer -> balanced
    pref_anon = pipeline._resolve_engineer_preference("alice")
    assert pref_anon["style"] == "balanced"


# ==============================================================================
# 6. DEV TUNING HARNESS BENCHMARK TEST
# ==============================================================================

def test_dev_tuning_harness_accuracy_target():
    """Verifies that the recall pipeline achieves >= 80% Top-3 accuracy on the 10 dev incidents."""
    report = run_tuning_suite(verbose=False)

    assert report.total_incidents == 10
    assert report.benchmark_passed is True
    assert report.top_3_accuracy_pct >= 80.0
    assert report.top_1_accuracy_pct >= 70.0
    assert report.failed_fix_warning_hits >= 8


# ==============================================================================
# 7. SSE PAYLOAD FORMATTING TESTS
# ==============================================================================

def test_sse_payload_formatting():
    pipeline = RecallPipeline(memory_store=HISTORICAL_MEMORY_CORPUS)
    result = pipeline.execute_tripartite_recall(
        service_name="payments-db",
        symptom="HikariCP connection pool exhausted",
        recent_deploy_diff="Bumped max-pool-size to 10",
        engineer_id="priya",
    )

    sse_events = RecallPipeline.format_for_sse(result)

    assert "memory_citation" in sse_events
    assert "failed_fix_warning" in sse_events
    assert "standing_directive" in sse_events
    assert "engineer_preference_applied" in sse_events

    # Verify memory citation format
    first_citation = sse_events["memory_citation"][0]
    assert first_citation["event"] == "memory_citation"
    assert first_citation["data"]["bank_id"] == "kartly-sre"
    assert "incident_id" in first_citation["data"]
    assert "relevance_score" in first_citation["data"]

    # Verify engineer preference event format
    pref_event = sse_events["engineer_preference_applied"][0]
    assert pref_event["event"] == "engineer_preference_applied"
    assert pref_event["data"]["engineer_id"] == "priya"
    assert pref_event["data"]["style"] == "concise"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
