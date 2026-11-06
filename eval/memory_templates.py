"""
RecallOps Standardized Retain Templates for Hindsight Cloud
Author: Member 4 (AI/ML & Model)
Phase: Phase 1: Foundations (H2–H8)

Defines structured retain formatters and data contracts for:
1. Incident Postmortems (`kartly-sre`, context: `incident_postmortem`)
2. Fix Attempts & Negative Memory (`kartly-sre`, context: `fix_outcome`)
3. Engineer Style Preferences (`engineer-{engineer_id}`, context: `user_preference`)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


# ==============================================================================
# CONSTANTS & NAMESPACES
# ==============================================================================

SHARED_SRE_BANK = "kartly-sre"
ENGINEER_BANK_PREFIX = "engineer-"

CONTEXT_INCIDENT_POSTMORTEM = "incident_postmortem"
CONTEXT_FIX_OUTCOME = "fix_outcome"
CONTEXT_USER_PREFERENCE = "user_preference"


class FixOutcome(str, Enum):
    """Execution outcome of a diagnostic or remediation attempt."""
    FAILED = "FAILED"
    WORKED = "WORKED"
    PARTIAL = "PARTIAL"


class OutputStyle(str, Enum):
    """Engineer output verbosity and presentation style."""
    CONCISE = "concise"
    DETAILED = "detailed"
    BALANCED = "balanced"


# ==============================================================================
# PYDANTIC SCHEMAS FOR MEMORY RETENTION
# ==============================================================================

class HindsightRetainPayload(BaseModel):
    """
    Standardized payload contract submitted to Hindsight Cloud retain API.
    Used by Member 1 (Backend) and Member 3 (Database).
    """
    model_config = ConfigDict(extra="forbid")

    bank_id: str = Field(
        ...,
        description="Target memory bank namespace (e.g. 'kartly-sre' or 'engineer-priya').",
    )
    content: str = Field(
        ...,
        description="Standardized plain-text memory string optimized for embedding and lexical recall.",
    )
    context: str = Field(
        ...,
        description="Category/context tag ('incident_postmortem', 'fix_outcome', or 'user_preference').",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured key-value attributes for filtering and audit logs.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of retention.",
    )


class IncidentPostmortemData(BaseModel):
    """Input parameters for formatting an incident postmortem memory."""
    incident_id: str = Field(..., description="Unique incident identifier (e.g. 'INC-1987')")
    service_name: str = Field(..., description="Name of affected service (e.g. 'payments-db')")
    root_cause_family: str = Field(..., description="Taxonomy classification (e.g. 'db_connection_leak')")
    symptom: str = Field(..., description="Observed error symptoms and metrics")
    attempted_fixes_and_outcomes: str = Field(..., description="Summary of actions tried and whether they worked/failed")
    root_cause: str = Field(..., description="Verified primary root cause")
    successful_fix: str = Field(..., description="Remediation action that resolved the incident")
    duration_min: int = Field(..., ge=1, description="Mean-Time-To-Recovery (MTTR) in minutes")


class FixAttemptData(BaseModel):
    """Input parameters for formatting a single remediation attempt / negative memory."""
    incident_id: str = Field(..., description="Associated incident ID (e.g. 'INC-1987')")
    service_name: str = Field(..., description="Service component acted upon")
    action: str = Field(..., description="Concrete action attempted (e.g. 'kubectl rollout restart deployment')")
    outcome: FixOutcome = Field(..., description="Result of attempt: FAILED, WORKED, or PARTIAL")
    notes: str = Field(..., description="Consequences, failure mode, or observed side-effects")


class EngineerPreferenceData(BaseModel):
    """Input parameters for formatting an engineer's personal output style preference."""
    engineer_id: str = Field(..., description="Engineer username or ID (e.g. 'priya', 'rahul')")
    style: Union[OutputStyle, Literal["concise", "detailed", "balanced"]] = Field(
        ..., description="Preference style keyword"
    )
    preference_string: str = Field(..., description="Detailed preference directive")


# ==============================================================================
# STANDARDIZED FORMATTERS
# ==============================================================================

def normalize_engineer_bank_id(engineer_id: str) -> str:
    """Ensures consistent 'engineer-{engineer_id}' bank naming format."""
    clean_id = engineer_id.strip().lower()
    if clean_id.startswith(ENGINEER_BANK_PREFIX):
        return clean_id
    return f"{ENGINEER_BANK_PREFIX}{clean_id}"


def format_incident_retain_payload(
    incident_id: str,
    service_name: str,
    root_cause_family: str,
    symptom: str,
    attempted_fixes_and_outcomes: str,
    root_cause: str,
    successful_fix: str,
    duration_min: int,
    metadata: Optional[Dict[str, Any]] = None,
) -> HindsightRetainPayload:
    """
    Formats a completed incident postmortem into the standardized Hindsight retain contract.

    Format:
    `[<incident_id>][<service_name>][family: <root_cause_family>] Symptom: <symptom>. Tried: <attempted_fixes_and_outcomes>. Root cause: <root_cause>. Fix: <successful_fix>. Time to resolve: <duration_min> min.`
    Target Bank: `kartly-sre`
    Context: `incident_postmortem`
    """
    content = (
        f"[{incident_id}][{service_name}][family: {root_cause_family}] "
        f"Symptom: {symptom}. "
        f"Tried: {attempted_fixes_and_outcomes}. "
        f"Root cause: {root_cause}. "
        f"Fix: {successful_fix}. "
        f"Time to resolve: {duration_min} min."
    )

    meta = {
        "incident_id": incident_id,
        "service_name": service_name,
        "root_cause_family": root_cause_family,
        "duration_min": duration_min,
        **(metadata or {}),
    }

    return HindsightRetainPayload(
        bank_id=SHARED_SRE_BANK,
        content=content,
        context=CONTEXT_INCIDENT_POSTMORTEM,
        metadata=meta,
    )


def format_fix_attempt_payload(
    incident_id: str,
    service_name: str,
    action: str,
    outcome: Union[FixOutcome, str],
    notes: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> HindsightRetainPayload:
    """
    Formats a single fix attempt into the standardized negative-memory/remediation contract.

    Format:
    `[<incident_id>][<service_name>] Action: <action> -> Outcome: <FAILED|WORKED|PARTIAL>. Notes: <notes>`
    Target Bank: `kartly-sre`
    Context: `fix_outcome`
    """
    outcome_str = outcome.value if isinstance(outcome, FixOutcome) else str(outcome).upper()
    content = f"[{incident_id}][{service_name}] Action: {action} -> Outcome: {outcome_str}. Notes: {notes}"

    meta = {
        "incident_id": incident_id,
        "service_name": service_name,
        "action": action,
        "outcome": outcome_str,
        "is_negative_memory": (outcome_str == FixOutcome.FAILED.value),
        **(metadata or {}),
    }

    return HindsightRetainPayload(
        bank_id=SHARED_SRE_BANK,
        content=content,
        context=CONTEXT_FIX_OUTCOME,
        metadata=meta,
    )


def format_engineer_preference_payload(
    engineer_id: str,
    style: Union[OutputStyle, str],
    preference_string: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> HindsightRetainPayload:
    """
    Formats an engineer's personal presentation and execution style preference.

    Format:
    `Engineer prefers <concise|detailed> output. Preference: <preference_string>`
    Target Bank: `engineer-{engineer_id}`
    Context: `user_preference`
    """
    style_str = style.value if isinstance(style, OutputStyle) else str(style).lower()
    bank_id = normalize_engineer_bank_id(engineer_id)
    content = f"Engineer prefers {style_str} output. Preference: {preference_string}"

    meta = {
        "engineer_id": engineer_id,
        "style": style_str,
        **(metadata or {}),
    }

    return HindsightRetainPayload(
        bank_id=bank_id,
        content=content,
        context=CONTEXT_USER_PREFERENCE,
        metadata=meta,
    )


# ==============================================================================
# PRE-CONFIGURED SEED PREFERENCE TEMPLATES
# ==============================================================================

SEED_PRIYA_PREFERENCE = format_engineer_preference_payload(
    engineer_id="priya",
    style=OutputStyle.CONCISE,
    preference_string="Prefers concise output: provide exact copy-ready kubectl commands only, skip verbose architectural explanations.",
    metadata={"role": "Lead Kubernetes On-Call", "tier": "tier-1"},
)

SEED_RAHUL_PREFERENCE = format_engineer_preference_payload(
    engineer_id="rahul",
    style=OutputStyle.DETAILED,
    preference_string="Prefers detailed root-cause analysis and comprehensive step-by-step remediation plans.",
    metadata={"role": "Principal Systems Architect", "tier": "tier-2"},
)


def get_seed_engineer_preference(engineer_id: str) -> Optional[HindsightRetainPayload]:
    """Retrieves seed preference for a designated engineer if pre-configured."""
    clean_id = engineer_id.strip().lower().removeprefix("engineer-")
    if clean_id == "priya":
        return SEED_PRIYA_PREFERENCE
    elif clean_id == "rahul":
        return SEED_RAHUL_PREFERENCE
    return None


def get_all_seed_preferences() -> List[HindsightRetainPayload]:
    """Returns all pre-configured seed preference payloads for bootstrap initialization."""
    return [SEED_PRIYA_PREFERENCE, SEED_RAHUL_PREFERENCE]
