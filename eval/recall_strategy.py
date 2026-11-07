"""
RecallOps Multi-Bank Recall Strategy & Citation Validation (Phase 1)
Author: Member 4 (AI/ML & Model)
Phase: Phase 1: Foundations (H2–H8)

Defines:
1. `build_recall_queries`: Dispatches targeted queries to organizational (`kartly-sre`)
   and personal (`engineer-{engineer_id}`) memory banks.
2. Citation verification and sanitization logic to detect hallucinations and ensure
   only verified incident IDs are presented to SREs.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field, ConfigDict

from eval.memory_templates import (
    SHARED_SRE_BANK,
    CONTEXT_INCIDENT_POSTMORTEM,
    CONTEXT_FIX_OUTCOME,
    CONTEXT_USER_PREFERENCE,
    normalize_engineer_bank_id,
)
from backend.app.schemas.agent_tools import AgentTriageResponse


# ==============================================================================
# RECALL QUERY SCHEMAS
# ==============================================================================

class SingleRecallQuery(BaseModel):
    """Specification for an individual retrieval request to Hindsight Cloud."""
    model_config = ConfigDict(extra="forbid")

    bank_id: str = Field(..., description="Target Hindsight memory bank namespace")
    query: str = Field(..., description="Natural language search query")
    context: Optional[str] = Field(None, description="Optional context tag filter")
    budget: str = Field(default="mid", description="Retrieval search budget ('low', 'mid', 'high')")
    limit: int = Field(default=3, ge=1, le=20, description="Maximum items to return")


class MultiBankRecallPlan(BaseModel):
    """Bundle of all 3 recall queries required for an incident triage session."""
    incident_query: SingleRecallQuery
    failed_fix_query: SingleRecallQuery
    preference_query: SingleRecallQuery

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return {
            "incident_query": self.incident_query.model_dump(),
            "failed_fix_query": self.failed_fix_query.model_dump(),
            "preference_query": self.preference_query.model_dump(),
        }


# ==============================================================================
# 1. QUERY BUILDER
# ==============================================================================

def build_recall_queries(
    service_name: str,
    symptom: str,
    engineer_id: str,
) -> Dict[str, Dict[str, Any]]:
    """
    Constructs the tripartite recall queries required for Phase 1 agent triage:
    1. `incident_query`: Symptom + service search in `kartly-sre` (budget='mid')
    2. `failed_fix_query`: Negative-memory search for failed actions in `kartly-sre` (budget='mid')
    3. `preference_query`: User style preference in `engineer-{engineer_id}` (budget='low')

    Args:
        service_name: Affected service (e.g. 'payments-db', 'checkout-api')
        symptom: Observed incident error or behavior (e.g. 'connection pool exhausted')
        engineer_id: On-call engineer handle (e.g. 'priya', 'rahul')

    Returns:
        Dictionary mapping query name to its retrieval parameters.
    """
    clean_service = service_name.strip()
    clean_symptom = symptom.strip()
    engineer_bank = normalize_engineer_bank_id(engineer_id)

    # 1. Episodic Incident Query (kartly-sre)
    incident_req = SingleRecallQuery(
        bank_id=SHARED_SRE_BANK,
        query=f"service: {clean_service} symptom: {clean_symptom} root cause and resolution postmortem",
        context=CONTEXT_INCIDENT_POSTMORTEM,
        budget="mid",
        limit=3,
    )

    # 2. Negative-Memory Failed Fixes Query (kartly-sre)
    failed_fix_req = SingleRecallQuery(
        bank_id=SHARED_SRE_BANK,
        query=f"FAILED unsuccessful fix attempt anti-pattern warning for {clean_service}: {clean_symptom}",
        context=CONTEXT_FIX_OUTCOME,
        budget="mid",
        limit=5,
    )

    # 3. User Style Preference Query (engineer-{engineer_id})
    preference_req = SingleRecallQuery(
        bank_id=engineer_bank,
        query="engineer output presentation style preference concise detailed kubectl commands format",
        context=CONTEXT_USER_PREFERENCE,
        budget="low",
        limit=1,
    )

    plan = MultiBankRecallPlan(
        incident_query=incident_req,
        failed_fix_query=failed_fix_req,
        preference_query=preference_req,
    )

    return plan.to_dict()


# ==============================================================================
# 2. CITATION VALIDATION & SANITIZATION
# ==============================================================================

# Regex matching standard Incident IDs (e.g. INC-1987, INC-2041, INC-102)
INCIDENT_ID_PATTERN = re.compile(r"\bINC-\d+\b", re.IGNORECASE)


def extract_incident_citations(text: str) -> List[str]:
    """
    Extracts all incident identifiers (e.g. 'INC-1987') appearing in a text block,
    preserving order of appearance and eliminating duplicates.
    """
    if not text:
        return []
    matches = INCIDENT_ID_PATTERN.findall(text)
    # Deduplicate while preserving order
    seen: Set[str] = set()
    ordered_unique: List[str] = []
    for m in matches:
        canonical = m.upper()
        if canonical not in seen:
            seen.add(canonical)
            ordered_unique.append(canonical)
    return ordered_unique


def validate_citations(
    cited_ids: List[str],
    available_incident_ids: List[str],
) -> Tuple[List[str], List[str]]:
    """
    Partitions cited incident IDs into valid recalled references vs. hallucinations.

    Args:
        cited_ids: List of incident IDs cited by the agent (e.g. ['INC-1987', 'INC-9999'])
        available_incident_ids: Genuine incident IDs present in recalled memory

    Returns:
        Tuple of (valid_citations, hallucinated_citations)
    """
    valid_set = {x.upper() for x in available_incident_ids}
    valid_citations: List[str] = []
    hallucinations: List[str] = []

    for cid in cited_ids:
        canonical = cid.strip().upper()
        if canonical in valid_set:
            if canonical not in valid_citations:
                valid_citations.append(canonical)
        else:
            if canonical not in hallucinations:
                hallucinations.append(canonical)

    return valid_citations, hallucinations


def sanitize_agent_response(
    response: AgentTriageResponse,
    recalled_incident_ids: List[str],
) -> AgentTriageResponse:
    """
    Sanitizes an AgentTriageResponse instance by:
    1. Verifying that all `cited_incident_ids` exist in `recalled_incident_ids`.
    2. Stripping hallucinated citations.
    3. If no genuine memory matches exist, ensuring the hypothesis explicitly
       acknowledges 'No historical memory match found.'
    """
    valid_citations, hallucinations = validate_citations(
        cited_ids=response.cited_incident_ids,
        available_incident_ids=recalled_incident_ids,
    )

    hypothesis = response.hypothesis
    # If the model cited hallucinated IDs in the text, warn or adjust
    if not valid_citations and not recalled_incident_ids:
        if "no historical memory match found" not in hypothesis.lower():
            hypothesis = f"{hypothesis.rstrip()} [Note: No historical memory match found.]"

    return AgentTriageResponse(
        incident_id=response.incident_id,
        hypothesis=hypothesis,
        confidence=response.confidence,
        cited_incident_ids=valid_citations,
        failed_fixes_warning=response.failed_fixes_warning,
        recommended_action=response.recommended_action,
        likely_owner=response.likely_owner,
    )
