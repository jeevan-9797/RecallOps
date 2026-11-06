"""
RecallOps REST API Request and Response Schemas (Pydantic v2).
Defines contracts for frozen endpoints:
- POST /api/alerts
- POST /api/incidents/{id}/triage
- POST /api/incidents/{id}/feedback
- POST /api/incidents/{id}/resolve
- GET /api/incidents/{id}/memories
- GET /api/observations
- GET /api/metrics/learning-curve
- POST /api/demo/reset
- GET /health
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


# ==============================================================================
# 1. ALERT INGESTION CONTRACTS (/api/alerts)
# ==============================================================================

class AlertCreateRequest(BaseModel):
    """Payload for submitting an operational alert to trigger RecallOps triage."""
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(
        ...,
        min_length=1,
        description="Name of the affected service (e.g., 'checkout-api', 'payments-db').",
        examples=["checkout-api"],
    )
    symptom: str = Field(
        ...,
        min_length=1,
        description="Observed anomaly, error spike, or alert message.",
        examples=["HTTP 500 spike and p99 latency > 2.5s post release v2.4.1"],
    )
    severity: str = Field(
        default="CRITICAL",
        description="Alert severity level (CRITICAL, HIGH, MEDIUM, LOW).",
        examples=["CRITICAL"],
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Timestamp when alert occurred (defaults to now).",
    )


class AlertCreateResponse(BaseModel):
    """Response returned upon successfully registering an incident from an alert."""
    incident_id: str = Field(..., description="Unique generated incident identifier (e.g., 'INC-2045').")
    status: str = Field(default="created", description="Current lifecycle state of the incident.")
    created_at: datetime = Field(..., description="Timestamp of incident creation.")


# ==============================================================================
# 2. HUMAN-IN-THE-LOOP FEEDBACK CONTRACTS (/api/incidents/{id}/feedback)
# ==============================================================================

class FeedbackCreateRequest(BaseModel):
    """Payload submitted when an on-call engineer accepts, rejects, or adjusts a recommendation."""
    model_config = ConfigDict(extra="forbid")

    suggestion_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the specific recommendation being evaluated.",
        examples=["SUG-902"],
    )
    outcome: Literal["worked", "failed", "partial"] = Field(
        ...,
        description="Real-world outcome of the attempted fix ('worked', 'failed', or 'partial').",
    )
    attempted_action: Optional[str] = Field(
        default=None,
        description="The concrete command, script, or operational remedy attempted.",
        examples=["systemctl restart postgresql"],
    )
    note: Optional[str] = Field(
        default=None,
        description="Contextual engineering notes explaining why the action succeeded or failed.",
        examples=["Restart cleared cache and caused 100% disk thrashing cascading to checkout-api."],
    )


class FeedbackCreateResponse(BaseModel):
    """Response returned after recording engineer feedback."""
    incident_id: str = Field(..., description="Target incident ID.")
    status: str = Field(default="recorded", description="Status of the feedback ingestion.")
    negative_memory_retained: bool = Field(
        default=False,
        description="Indicates whether this feedback was retained into Hindsight negative memory.",
    )


# ==============================================================================
# 3. INCIDENT RESOLUTION CONTRACTS (/api/incidents/{id}/resolve)
# ==============================================================================

class ResolveIncidentRequest(BaseModel):
    """Payload for officially closing an incident with a verified postmortem."""
    model_config = ConfigDict(extra="forbid")

    root_cause: str = Field(
        ...,
        min_length=1,
        description="Verified root cause of the incident.",
        examples=["Database connection pool exhaustion caused by unindexed query on orders.customer_id"],
    )
    fix: str = Field(
        ...,
        min_length=1,
        description="Successful remediation action that stabilized the service.",
        examples=["Rolled back release v2.4.1 and applied PgBouncer pooler connection cap."],
    )
    duration_min: int = Field(
        ...,
        ge=1,
        description="Total duration of the outage in minutes (MTTR).",
        examples=[14],
    )


class ResolveIncidentResponse(BaseModel):
    """Response returned after resolving incident and generating postmortem."""
    incident_id: str = Field(..., description="Target incident ID.")
    status: str = Field(default="resolved", description="Status of the resolution.")
    episodic_memory_retained: bool = Field(
        default=False,
        description="Indicates whether this postmortem was retained into Hindsight episodic memory.",
    )


# ==============================================================================
# 4. MEMORIES RETRIEVAL CONTRACTS (/api/incidents/{id}/memories)
# ==============================================================================

class MemoriesResponse(BaseModel):
    """Response payload for displaying recalled memories in the frontend Memory Panel."""
    incident_id: str = Field(..., description="Incident ID for which memories were recalled.")
    count: int = Field(..., description="Total number of memories referenced.")
    memories: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of recalled positive episodic and negative memory records.",
    )


# ==============================================================================
# 5. LEARNED PATTERNS CONTRACTS (/api/observations)
# ==============================================================================

class ObservationsResponse(BaseModel):
    """Synthesized observations generated by Hindsight reflect() across incident history."""
    observations: List[str] = Field(
        default_factory=list,
        description="High-level learned operational observations.",
    )
    count: int = Field(..., description="Number of active observations.")
    source: str = Field(
        default="hindsight_reflect",
        description="Origin of the observations (e.g., 'hindsight_reflect', 'mock_baseline').",
    )


# ==============================================================================
# 6. LEARNING CURVE BENCHMARK METRICS (/api/metrics/learning-curve)
# ==============================================================================

class LearningCurveMetricsResponse(BaseModel):
    """Deterministic learning-curve metrics comparing memory OFF vs ON over replayed incidents."""
    total_incidents_replayed: int = Field(..., description="Number of incidents in the evaluation benchmark.")
    accuracy_memory_off: float = Field(..., description="Diagnostic accuracy with Hindsight memory disabled (0.0 - 1.0).")
    accuracy_memory_on: float = Field(..., description="Diagnostic accuracy with Hindsight memory enabled (0.0 - 1.0).")
    avg_mttr_memory_off_min: float = Field(..., description="Average MTTR in minutes with memory disabled.")
    avg_mttr_memory_on_min: float = Field(..., description="Average MTTR in minutes with memory enabled.")
    negative_fix_avoidance_rate: float = Field(..., description="Percentage of known failed remediations rejected (target 100%).")
    benchmark_status: str = Field(default="ready", description="Status of the benchmark run.")


# ==============================================================================
# 7. DEMO 1-CLICK RESET CONTRACTS (/api/demo/reset)
# ==============================================================================

class DemoResetRequest(BaseModel):
    """Optional configuration for resetting demo environment state."""
    model_config = ConfigDict(extra="forbid")

    seed_days: Optional[int] = Field(
        default=180,
        ge=1,
        le=365,
        description="Lookback window in days for synthetic incident history seeding.",
    )


class DemoResetResponse(BaseModel):
    """Response returned upon wiping and reseeding system state for demo."""
    status: str = Field(default="reset_complete", description="Outcome status.")
    message: str = Field(..., description="Summary of reseeding operations.")
    services_seeded: int = Field(..., description="Count of microservices configured.")
    deploys_seeded: int = Field(..., description="Count of deployment events seeded.")
    memories_seeded: int = Field(..., description="Count of historical memories seeded.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 8. HEALTH CHECK CONTRACT (/health)
# ==============================================================================

class HealthCheckResponse(BaseModel):
    """Liveness check status and component readiness report."""
    status: str = Field(default="healthy", description="Overall service liveness state.")
    version: str = Field(..., description="API version string.")
    environment: str = Field(..., description="Runtime environment identifier.")
    checks: Dict[str, str] = Field(
        ...,
        description="Factual readiness state of external integrations (never spoofed as connected).",
    )
