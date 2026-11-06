"""
Incidents API Router.
Handles:
- POST /api/incidents/{id}/triage (SSE Stream)
- POST /api/incidents/{id}/feedback (Human-in-the-loop)
- POST /api/incidents/{id}/resolve (Resolution & postmortem)
- GET /api/incidents/{id}/memories (Memory Panel feed)
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse

from backend.app.api.alerts import ACTIVE_INCIDENTS
from backend.app.core.exceptions import IncidentNotFoundError
from backend.app.core.sse import SSEEventTypes, format_sse
from backend.app.schemas.api_models import (
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    MemoriesResponse,
    ResolveIncidentRequest,
    ResolveIncidentResponse,
)

router = APIRouter(prefix="/incidents", tags=["Incidents"])


async def generate_mock_triage_stream(
    incident_id: str,
    memory_enabled: bool,
) -> AsyncGenerator[str, None]:
    """
    Generates deterministic SSE event stream for Phase 0 frontend unblocking.
    Demonstrates the difference between Memory ON and Memory OFF.
    """
    # 1. Initial Thought
    yield format_sse(
        SSEEventTypes.THOUGHT,
        {
            "step": 1,
            "content": f"Alert received for {incident_id}. Fetching telemetry logs and checking recent releases...",
            "mode": "mock_p0",
        },
    )
    await asyncio.sleep(0.05)

    # 2. Tool Call: get_logs
    yield format_sse(
        SSEEventTypes.TOOL_CALL,
        {
            "tool": "get_logs",
            "arguments": {"service_name": "checkout-api", "incident_id": incident_id, "limit": 50},
        },
    )
    await asyncio.sleep(0.05)

    # 3. Tool Result: get_logs
    yield format_sse(
        SSEEventTypes.TOOL_RESULT,
        {
            "tool": "get_logs",
            "summary": "15 ERROR traces found: ConnectionPoolExhausted. Active pool size: 200/200.",
        },
    )
    await asyncio.sleep(0.05)

    # 4. Tool Call: get_recent_deploys
    yield format_sse(
        SSEEventTypes.TOOL_CALL,
        {
            "tool": "get_recent_deploys",
            "arguments": {"service_name": "checkout-api", "lookback_hours": 24},
        },
    )
    await asyncio.sleep(0.05)

    yield format_sse(
        SSEEventTypes.TOOL_RESULT,
        {
            "tool": "get_recent_deploys",
            "summary": "Release v2.4.1 deployed 22 minutes ago by @dev-rahul (commit a9f4c12).",
        },
    )
    await asyncio.sleep(0.05)

    if memory_enabled:
        # 5. Tool Call: recall_similar_incidents
        yield format_sse(
            SSEEventTypes.TOOL_CALL,
            {
                "tool": "recall_similar_incidents",
                "arguments": {"service_name": "checkout-api", "symptom": "Connection pool full", "limit": 3},
            },
        )
        await asyncio.sleep(0.05)

        # 6. Recalled Memory Event (standardized memory_hit event)
        memory_payload = {
            "memory_type": "episodic_resolution",
            "incident_id": "INC-1987",
            "similarity": 0.94,
            "relative_time": "6 weeks ago",
            "symptom": "FATAL: remaining connection slots are reserved for non-replication superuser connections",
            "root_cause": "Unindexed query in orders table during campaign traffic spike",
            "successful_fix": "Rolled back pool changes and applied PgBouncer pooler cap.",
        }
        yield format_sse(SSEEventTypes.MEMORY_HIT, memory_payload)
        yield format_sse(SSEEventTypes.RECALLED_MEMORY, memory_payload)
        await asyncio.sleep(0.05)

        # 7. Tool Call: recall_failed_fixes
        yield format_sse(
            SSEEventTypes.TOOL_CALL,
            {
                "tool": "recall_failed_fixes",
                "arguments": {"service_name": "payments-db", "incident_signature": "ConnectionPoolExhausted"},
            },
        )
        await asyncio.sleep(0.05)

        # 8. Negative Memory Warning
        yield format_sse(
            SSEEventTypes.WARNING,
            {
                "type": "negative_memory_block",
                "directive": "Do NOT restart payments-db: failed 2x in Sept (INC-1987). Cold cache cleared buffer pool causing 100% disk thrashing.",
            },
        )
        await asyncio.sleep(0.05)

        # 9. Suggestion (Targeted SRE Resolution)
        yield format_sse(
            SSEEventTypes.SUGGESTION,
            {
                "incident_id": incident_id,
                "hypothesis": "Database connection pool exhaustion caused by unindexed query introduced in release v2.4.1.",
                "confidence": 0.94,
                "cited_incident_ids": ["INC-1987"],
                "failed_fixes_warning": [
                    "Do NOT restart payments-db: failed 2x in Sept and caused cascade outage",
                ],
                "recommended_action": "Rollback checkout-api to release v2.4.0 and apply hotfix index on orders.customer_id.",
                "likely_owner": "payments-platform-team (@alice-sre)",
                "memory_augmented": True,
            },
        )
    else:
        # Memory Disabled: Generic Naive Baseline
        yield format_sse(
            SSEEventTypes.SUGGESTION,
            {
                "incident_id": incident_id,
                "hypothesis": "Possible high CPU or connection congestion.",
                "confidence": 0.45,
                "cited_incident_ids": [],
                "failed_fixes_warning": [],
                "recommended_action": "Restart checkout-api pods and scale replica count.",
                "likely_owner": "on-call-generalist",
                "memory_augmented": False,
            },
        )

    await asyncio.sleep(0.05)
    # 10. Done Event
    yield format_sse(
        SSEEventTypes.DONE,
        {
            "incident_id": incident_id,
            "status": "completed",
            "duration_ms": 320,
            "memory_enabled": memory_enabled,
            "mode": "mock_p0",
        },
    )


@router.post(
    "/{incident_id}/triage",
    summary="Execute SRE Incident Triage Stream (SSE)",
)
async def triage_incident(
    incident_id: str,
    memory: str = Query(default="on", pattern="^(on|off)$", description="Toggle Hindsight memory augmentation"),
):
    """
    Initiates the Autonomous SRE Agent triage loop over Server-Sent Events (SSE).
    Streams thoughts, tool invocations, recalled memories, anti-pattern warnings,
    and final actionable remediation plans.
    """
    memory_enabled = (memory.lower() == "on")
    return StreamingResponse(
        generate_mock_triage_stream(incident_id, memory_enabled),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{incident_id}/feedback",
    response_model=FeedbackCreateResponse,
    status_code=status.HTTP_200_OK,
    summary="Record Human Engineer Feedback",
)
async def submit_feedback(
    incident_id: str,
    payload: FeedbackCreateRequest,
) -> FeedbackCreateResponse:
    """
    Records engineer feedback (worked, failed, partial).
    If outcome is 'failed', marks for negative-memory retention into Hindsight.
    """
    incident = ACTIVE_INCIDENTS.get(incident_id)
    if not incident:
        # For mock testing, allow feedback on known sample IDs
        ACTIVE_INCIDENTS[incident_id] = {"id": incident_id, "feedback": []}
        incident = ACTIVE_INCIDENTS[incident_id]

    negative_retained = (payload.outcome == "failed")
    incident.setdefault("feedback", []).append({
        "suggestion_id": payload.suggestion_id,
        "outcome": payload.outcome,
        "attempted_action": payload.attempted_action,
        "note": payload.note,
        "timestamp": datetime.now(timezone.utc),
    })

    return FeedbackCreateResponse(
        incident_id=incident_id,
        status="recorded",
        negative_memory_retained=negative_retained,
    )


@router.post(
    "/{incident_id}/resolve",
    response_model=ResolveIncidentResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve Incident and Retain Postmortem",
)
async def resolve_incident(
    incident_id: str,
    payload: ResolveIncidentRequest,
) -> ResolveIncidentResponse:
    """
    Closes the incident, writes postmortem facts, and triggers episodic retention
    into Hindsight Cloud memory.
    """
    incident = ACTIVE_INCIDENTS.get(incident_id)
    if not incident:
        ACTIVE_INCIDENTS[incident_id] = {"id": incident_id}
        incident = ACTIVE_INCIDENTS[incident_id]

    incident["status"] = "resolved"
    incident["root_cause"] = payload.root_cause
    incident["fix"] = payload.fix
    incident["duration_min"] = payload.duration_min
    incident["resolved_at"] = datetime.now(timezone.utc)

    return ResolveIncidentResponse(
        incident_id=incident_id,
        status="resolved",
        episodic_memory_retained=True,
    )


@router.get(
    "/{incident_id}/memories",
    response_model=MemoriesResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Memories Used for Incident",
)
async def get_incident_memories(incident_id: str) -> MemoriesResponse:
    """
    Retrieves positive episodic and negative memory entries cited during triage
    for display in the frontend Memory Panel.
    """
    incident = ACTIVE_INCIDENTS.get(incident_id, {})
    memories = incident.get("memories", [
        {
            "memory_type": "episodic_resolution",
            "incident_id": "INC-1987",
            "similarity": 0.94,
            "relative_time": "6 weeks ago",
            "symptom": "Fatal connection slots exhausted during campaign",
            "root_cause": "Connection leak under traffic spike",
            "successful_fix": "Increased max_connections to 400 and deployed PgBouncer pooler",
        },
        {
            "memory_type": "failed_fix",
            "failed_fix_id": "FF-302",
            "incident_id": "INC-1987",
            "service_name": "payments-db",
            "attempted_action": "systemctl restart postgresql",
            "warning_directive": "Do NOT restart payments-db under active connection exhaustion.",
        },
    ])

    return MemoriesResponse(
        incident_id=incident_id,
        count=len(memories),
        memories=memories,
    )
