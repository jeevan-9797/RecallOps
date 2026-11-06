"""
RecallOps Agent Tool Schemas & Triage Response Contracts (Pydantic v2)
Author: Member 4 (AI/ML & Model)
Phase: Phase 0 Kickoff -> Phase 1 Foundation

Defines:
1. Pydantic input models for all 6 agent function calling tools.
2. The structured final agent triage response schema (`AgentTriageResponse`).
3. OpenAI / Groq compatible tool specification generator and constants.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


# ==============================================================================
# 1. TOOL INPUT SCHEMAS (Function Calling Arguments)
# ==============================================================================

class RecallSimilarIncidentsInput(BaseModel):
    """
    Input arguments for recalling historically resolved incidents matching
    symptom signatures from Hindsight episodic memory.
    """
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(
        ...,
        description="Name of the affected service or infrastructure component (e.g., 'checkout-api', 'payments-db').",
        min_length=1,
    )
    symptom: str = Field(
        ...,
        description="Primary symptom, error pattern, or observed anomaly string (e.g., 'HTTP 500 spike post deploy').",
        min_length=1,
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum number of historical similar incidents to recall from Hindsight episodic memory.",
    )


class RecallFailedFixesInput(BaseModel):
    """
    Input arguments for retrieving negative-memory entries (failed remediations,
    anti-patterns, or harmful actions attempted in past incidents).
    """
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(
        ...,
        description="Name of the affected service or infrastructure component.",
        min_length=1,
    )
    incident_signature: str = Field(
        ...,
        description="Error signature, stack trace fingerprint, or incident pattern used to query negative memory for failed remediation attempts.",
        min_length=1,
    )


class GetRecentDeploysInput(BaseModel):
    """
    Input arguments for querying the deployment registry for recent releases,
    configuration rollouts, or canary updates.
    """
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(
        ...,
        description="Target service name to query deployment history.",
        min_length=1,
    )
    lookback_hours: int = Field(
        default=24,
        ge=1,
        le=720,
        description="Hours to look back for recent deployments, canary rollouts, or config updates.",
    )


class GetLogsInput(BaseModel):
    """
    Input arguments for retrieving telemetry logs, error traces, and runtime
    events for an incident.
    """
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(
        ...,
        description="Service identifier whose logs need to be fetched.",
        min_length=1,
    )
    incident_id: str = Field(
        ...,
        description="Identifier of the active incident for correlated log querying (e.g., 'INC-2045').",
        min_length=1,
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of log entries to retrieve.",
    )


class GetServiceOwnerInput(BaseModel):
    """
    Input arguments for discovering service ownership, escalation points,
    and on-call contacts.
    """
    model_config = ConfigDict(extra="forbid")

    service_name: str = Field(
        ...,
        description="Name of the service to look up on-call engineers, squad lead, and escalation pathways.",
        min_length=1,
    )


class PostToBandRoomInput(BaseModel):
    """
    Input arguments for publishing real-time triage updates, hypotheses,
    or warnings to the incident war room (Band Room).
    """
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(
        ...,
        description="Target incident war room / band room identifier.",
        min_length=1,
    )
    message: str = Field(
        ...,
        description="Markdown-formatted message or structured update to post to the incident channel.",
        min_length=1,
    )
    sender: str = Field(
        default="Triage Agent",
        description="Display name or system identity of the entity posting to the room.",
        min_length=1,
    )


# ==============================================================================
# 2. FINAL STRUCTURED AGENT OUTPUT SCHEMA
# ==============================================================================

class AgentTriageResponse(BaseModel):
    """
    Structured final response schema produced by the RecallOps SRE agent
    upon completing incident triage, investigation, and root-cause synthesis.
    """
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "incident_id": "INC-2045",
                "hypothesis": "Database connection pool exhaustion caused by unindexed query introduced in release v2.4.1.",
                "confidence": 0.92,
                "cited_incident_ids": ["INC-1987", "INC-1842"],
                "failed_fixes_warning": [
                    "Do NOT restart payments-db: failed 2x in Sept and caused cascade outage",
                    "Do NOT increase thread pool beyond 200 without buffer pool resizing"
                ],
                "recommended_action": "Rollback payments-service to release v2.4.0 and apply hotfix index on orders.customer_id.",
                "likely_owner": "payments-platform-team (@alice-sre)"
            }
        }
    )

    incident_id: str = Field(
        ...,
        description="Unique identifier of the incident being triaged (e.g., 'INC-2045').",
        min_length=1,
    )
    hypothesis: str = Field(
        ...,
        description="Root cause hypothesis derived from symptoms, logs, deploys, and recalled historical incidents.",
        min_length=1,
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 representing certainty of the diagnosis and recommendation.",
    )
    cited_incident_ids: List[str] = Field(
        default_factory=list,
        description="List of historical incident IDs referenced as precedent or evidence (e.g., ['INC-1987']).",
    )
    failed_fixes_warning: List[str] = Field(
        default_factory=list,
        description="Critical warnings of remediation attempts that failed in past incidents and MUST NOT be repeated (negative memory).",
    )
    recommended_action: str = Field(
        ...,
        description="Actionable, prescriptive recommendation for resolving or mitigating the incident.",
        min_length=1,
    )
    likely_owner: str = Field(
        ...,
        description="Team, squad, or on-call engineer identified as the appropriate owner/resolver.",
        min_length=1,
    )


# ==============================================================================
# 3. OPENAI / GROQ TOOL DEFINITIONS BUILDER
# ==============================================================================

def _clean_json_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Clean Pydantic JSON schema to OpenAI function parameters format."""
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": schema.get("properties", {}),
        "required": schema.get("required", []),
    }
    return parameters


def build_tool_definition(
    name: str,
    description: str,
    input_model: type[BaseModel]
) -> Dict[str, Any]:
    """Generate OpenAI/Groq compatible tool specification from a Pydantic model."""
    raw_schema = input_model.model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description.strip(),
            "parameters": _clean_json_schema(raw_schema),
        },
    }


def get_openai_tool_definitions() -> List[Dict[str, Any]]:
    """
    Returns the complete list of 6 function calling tool definitions
    in OpenAI/Groq format ready to pass to `tools=` parameter.
    """
    return [
        build_tool_definition(
            name="recall_similar_incidents",
            description="Query past resolved incidents matching service name and symptom patterns from Hindsight vector/episodic memory.",
            input_model=RecallSimilarIncidentsInput,
        ),
        build_tool_definition(
            name="recall_failed_fixes",
            description="Retrieve negative-memory records of known failed remediations, anti-patterns, or harmful actions attempted for this incident signature to prevent repeating past mistakes.",
            input_model=RecallFailedFixesInput,
        ),
        build_tool_definition(
            name="get_recent_deploys",
            description="Fetch deployment history, commit hashes, authors, and rollout status for a service within a given lookback window.",
            input_model=GetRecentDeploysInput,
        ),
        build_tool_definition(
            name="get_logs",
            description="Retrieve recent log events and error traces for a specific service and incident.",
            input_model=GetLogsInput,
        ),
        build_tool_definition(
            name="get_service_owner",
            description="Find the primary on-call engineer, team lead, and escalation contact details for a given service.",
            input_model=GetServiceOwnerInput,
        ),
        build_tool_definition(
            name="post_to_band_room",
            description="Broadcast real-time triage updates, incident status, hypotheses, or escalation alerts to the virtual incident command/band room.",
            input_model=PostToBandRoomInput,
        ),
    ]


def get_agent_response_schema() -> Dict[str, Any]:
    """Returns the JSON Schema of AgentTriageResponse for structured outputs."""
    return AgentTriageResponse.model_json_schema()


# Precomputed static list for zero-overhead imports
TOOL_DEFINITIONS: List[Dict[str, Any]] = get_openai_tool_definitions()
