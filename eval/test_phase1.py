"""
Unit Tests for Phase 1: Memory Templates, System Prompts, and Recall Strategy
Author: Member 4 (AI/ML & Model)
Phase: Phase 1: Foundations (H2–H8)
"""

import pytest
from backend.app.prompts.system_prompts import (
    SENIOR_SRE_SYSTEM_PROMPT,
    build_sre_system_prompt,
)
from backend.app.schemas.agent_tools import AgentTriageResponse
from eval.memory_templates import (
    SHARED_SRE_BANK,
    CONTEXT_INCIDENT_POSTMORTEM,
    CONTEXT_FIX_OUTCOME,
    CONTEXT_USER_PREFERENCE,
    FixOutcome,
    OutputStyle,
    format_incident_retain_payload,
    format_fix_attempt_payload,
    format_engineer_preference_payload,
    get_seed_engineer_preference,
    get_all_seed_preferences,
    normalize_engineer_bank_id,
)
from eval.recall_strategy import (
    build_recall_queries,
    extract_incident_citations,
    validate_citations,
    sanitize_agent_response,
)


# ==============================================================================
# 1. SYSTEM PROMPTS & DYNAMIC ADAPTATION TESTS
# ==============================================================================

def test_senior_sre_system_prompt_content():
    prompt = SENIOR_SRE_SYSTEM_PROMPT
    assert "Kartly" in prompt
    assert "[INC-1987]" in prompt
    assert "No historical memory match found." in prompt
    assert "failed_fixes_warning" in prompt
    assert "Priya" in prompt
    assert "Rahul" in prompt
    assert "AgentTriageResponse" in prompt


def test_build_sre_system_prompt_dynamic_injection():
    # With Priya (concise) and active memories
    prompt = build_sre_system_prompt(
        engineer_id="priya",
        engineer_preference="Prefers concise kubectl commands only.",
        recalled_incident_memories="[INC-1987] DB connection pool exhausted.",
        recalled_failed_fixes="[INC-1987] Action: restart pods -> FAILED.",
    )

    assert "ACTIVE ON-CALL ENGINEER CONTEXT" in prompt
    assert "priya" in prompt
    assert "Prefers concise kubectl commands only." in prompt
    assert "[INC-1987] DB connection pool exhausted." in prompt
    assert "[INC-1987] Action: restart pods -> FAILED." in prompt


def test_build_sre_system_prompt_empty_memories_fallback():
    prompt = build_sre_system_prompt(
        engineer_id="rahul",
        recalled_incident_memories=None,
    )
    assert "No relevant historical incident memories were retrieved" in prompt
    assert "You MUST state: 'No historical memory match found.'" in prompt


# ==============================================================================
# 2. MEMORY TEMPLATES & RETAIN PAYLOAD TESTS
# ==============================================================================

def test_format_incident_retain_payload():
    payload = format_incident_retain_payload(
        incident_id="INC-1987",
        service_name="payments-db",
        root_cause_family="db_connection_leak",
        symptom="HTTP 500 error spike post-deploy",
        attempted_fixes_and_outcomes="Restarted pods (FAILED)",
        root_cause="Unindexed query in v2.4.1",
        successful_fix="Added index on orders.customer_id",
        duration_min=18,
    )

    assert payload.bank_id == SHARED_SRE_BANK
    assert payload.context == CONTEXT_INCIDENT_POSTMORTEM
    assert "[INC-1987][payments-db][family: db_connection_leak]" in payload.content
    assert "Symptom: HTTP 500 error spike post-deploy." in payload.content
    assert "Tried: Restarted pods (FAILED)." in payload.content
    assert "Root cause: Unindexed query in v2.4.1." in payload.content
    assert "Fix: Added index on orders.customer_id." in payload.content
    assert "Time to resolve: 18 min." in payload.content
    assert payload.metadata["incident_id"] == "INC-1987"
    assert payload.metadata["duration_min"] == 18


def test_format_fix_attempt_payload():
    payload = format_fix_attempt_payload(
        incident_id="INC-1987",
        service_name="payments-db",
        action="kubectl rollout restart deployment/payments-db",
        outcome=FixOutcome.FAILED,
        notes="Wiped cache and caused cold-start disk storm",
    )

    assert payload.bank_id == SHARED_SRE_BANK
    assert payload.context == CONTEXT_FIX_OUTCOME
    assert payload.content == (
        "[INC-1987][payments-db] Action: kubectl rollout restart deployment/payments-db -> Outcome: FAILED. "
        "Notes: Wiped cache and caused cold-start disk storm"
    )
    assert payload.metadata["is_negative_memory"] is True
    assert payload.metadata["outcome"] == "FAILED"


def test_format_engineer_preference_payload():
    payload = format_engineer_preference_payload(
        engineer_id="priya",
        style=OutputStyle.CONCISE,
        preference_string="Prefers concise output: provide exact copy-ready kubectl commands only, skip verbose architectural explanations.",
    )

    assert payload.bank_id == "engineer-priya"
    assert payload.context == CONTEXT_USER_PREFERENCE
    assert "Engineer prefers concise output. Preference: Prefers concise output:" in payload.content
    assert payload.metadata["engineer_id"] == "priya"
    assert payload.metadata["style"] == "concise"


def test_seed_engineer_preferences():
    priya = get_seed_engineer_preference("priya")
    assert priya is not None
    assert priya.bank_id == "engineer-priya"
    assert "kubectl" in priya.content

    rahul = get_seed_engineer_preference("rahul")
    assert rahul is not None
    assert rahul.bank_id == "engineer-rahul"
    assert "detailed root-cause" in rahul.content

    all_seeds = get_all_seed_preferences()
    assert len(all_seeds) == 2


def test_normalize_engineer_bank_id():
    assert normalize_engineer_bank_id("priya") == "engineer-priya"
    assert normalize_engineer_bank_id("engineer-priya") == "engineer-priya"
    assert normalize_engineer_bank_id("  RAHUL  ") == "engineer-rahul"


# ==============================================================================
# 3. RECALL STRATEGY & CITATION VALIDATION TESTS
# ==============================================================================

def test_build_recall_queries():
    queries = build_recall_queries(
        service_name="payments-db",
        symptom="connection pool exhausted",
        engineer_id="priya",
    )

    assert "incident_query" in queries
    assert "failed_fix_query" in queries
    assert "preference_query" in queries

    # Verify incident query
    inc_q = queries["incident_query"]
    assert inc_q["bank_id"] == SHARED_SRE_BANK
    assert inc_q["context"] == CONTEXT_INCIDENT_POSTMORTEM
    assert inc_q["budget"] == "mid"
    assert "payments-db" in inc_q["query"]

    # Verify failed fix query
    ff_q = queries["failed_fix_query"]
    assert ff_q["bank_id"] == SHARED_SRE_BANK
    assert ff_q["context"] == CONTEXT_FIX_OUTCOME
    assert ff_q["budget"] == "mid"
    assert "FAILED" in ff_q["query"]

    # Verify preference query
    pref_q = queries["preference_query"]
    assert pref_q["bank_id"] == "engineer-priya"
    assert pref_q["context"] == CONTEXT_USER_PREFERENCE
    assert pref_q["budget"] == "low"
    assert pref_q["limit"] == 1


def test_extract_incident_citations():
    text = "Diagnosis similar to [INC-1987] and INC-2041, but not INC-1987 again."
    citations = extract_incident_citations(text)
    assert citations == ["INC-1987", "INC-2041"]

    assert extract_incident_citations("") == []
    assert extract_incident_citations("No incident citations here.") == []


def test_validate_citations():
    available = ["INC-1987", "INC-1842"]
    cited = ["INC-1987", "INC-9999", "INC-1842", "INC-7777"]

    valid, hallucinations = validate_citations(cited, available)
    assert valid == ["INC-1987", "INC-1842"]
    assert hallucinations == ["INC-9999", "INC-7777"]


def test_sanitize_agent_response_strips_hallucinations():
    raw_response = AgentTriageResponse(
        incident_id="INC-2045",
        hypothesis="Caused by connection pool leak like in [INC-1987] and [INC-9999]",
        confidence=0.88,
        cited_incident_ids=["INC-1987", "INC-9999"],  # INC-9999 is hallucinated
        failed_fixes_warning=["Do NOT restart pods"],
        recommended_action="kubectl scale deployment --replicas=3",
        likely_owner="payments-platform",
    )

    sanitized = sanitize_agent_response(
        response=raw_response,
        recalled_incident_ids=["INC-1987"],
    )

    # Hallucinated ID stripped
    assert sanitized.cited_incident_ids == ["INC-1987"]
    assert "INC-9999" not in sanitized.cited_incident_ids


def test_sanitize_agent_response_no_memory_disclaimer():
    raw_response = AgentTriageResponse(
        incident_id="INC-2045",
        hypothesis="Disk saturated due to unindexed temp table files.",
        confidence=0.65,
        cited_incident_ids=[],
        failed_fixes_warning=[],
        recommended_action="Run vacuum and clean temp tables",
        likely_owner="infra-team",
    )

    sanitized = sanitize_agent_response(
        response=raw_response,
        recalled_incident_ids=[],  # No memory retrieved
    )

    assert "No historical memory match found." in sanitized.hypothesis
