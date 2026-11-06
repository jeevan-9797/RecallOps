"""
Incidents API Router.
Handles:
- POST /api/incidents/{id}/triage (Real AI ReAct SSE Stream + ?memory=on|off + engineer preference)
- POST /api/incidents/{id}/feedback (PostgreSQL persistence + Hindsight negative/preference retention)
- POST /api/incidents/{id}/resolve (PostgreSQL resolution + Hindsight organizational postmortem retention)
- GET /api/incidents/{id}/memories (Memory Panel feed from unified dual memory)
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.alerts import ACTIVE_INCIDENTS
from backend.app.core.exceptions import IncidentNotFoundError
from backend.app.core.sse import SSEEventTypes, format_sse
from backend.app.db.repository import SQLAlchemyRepository
from backend.app.db.session import get_db_session
from backend.app.schemas.api_models import (
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    MemoriesResponse,
    ResolveIncidentRequest,
    ResolveIncidentResponse,
)
from backend.app.services.band_adapter import band_adapter
from backend.app.services.groq_agent import GroqAgent
from backend.app.services.hindsight_service import hindsight_service
from backend.app.services.tool_handlers import AgentToolDispatcher

logger = logging.getLogger("recallops.api.incidents")

router = APIRouter(prefix="/incidents", tags=["Incidents"])


@router.post(
    "/{incident_id}/triage",
    summary="Execute SRE Incident Triage Stream (SSE)",
)
async def triage_incident(
    incident_id: str,
    memory: str = Query(default="on", pattern="^(on|off)$", description="Toggle Hindsight memory augmentation"),
    engineer_id: Optional[str] = Query(default=None, description="Optional engineer ID for personalized workflow preferences"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Initiates the Autonomous SRE Agent triage loop over Server-Sent Events (SSE).
    Streams thoughts, tool invocations, recalled memories, anti-pattern warnings,
    and final actionable remediation plans.
    """
    memory_enabled = (memory.lower() == "on")
    repo = SQLAlchemyRepository(session)
    dispatcher = AgentToolDispatcher(db_repo=repo, hindsight=hindsight_service, band=band_adapter)
    agent = GroqAgent(tool_dispatcher=dispatcher, db_repo=repo, hindsight=hindsight_service)

    # 1. Resolve incident telemetry context
    inc_data = await repo.get_incident(incident_id)
    if inc_data:
        service_name = inc_data.get("service_name") or "checkout-api"
        symptom = inc_data.get("symptom") or "Service latency degradation and error spike"
    else:
        active = ACTIVE_INCIDENTS.get(incident_id, {})
        service_name = active.get("service_name", "checkout-api")
        symptom = active.get("symptom", "HTTP 500 spike and p99 latency > 2.5s post release v2.4.1")

    async def event_generator():
        try:
            async for event_type, data in agent.stream_triage_loop(
                incident_id=incident_id,
                service_name=service_name,
                symptom=symptom,
                memory_enabled=memory_enabled,
                engineer_id=engineer_id,
            ):
                # Standard event emission
                yield format_sse(event_type, data)

                # Emit backward-compatible event for memory_hit
                if event_type == "memory_hit":
                    yield format_sse("recalled_memory", data)

                # Record agent suggestion in DB for metrics tracking
                if event_type == "suggestion":
                    try:
                        await repo.record_agent_suggestion(
                            incident_code=incident_id,
                            suggestion={
                                "hypothesis": data.get("hypothesis", ""),
                                "rank": 1,
                                "memory_on": memory_enabled,
                            },
                        )
                    except Exception as err:
                        logger.warning(f"Could not persist agent suggestion to DB: {err}")

        except asyncio.CancelledError:
            logger.info(f"SSE client disconnected for incident {incident_id}")
            raise
        except Exception as e:
            logger.error(f"Error in triage SSE stream for {incident_id}: {e}", exc_info=True)
            yield format_sse(
                "error",
                {"incident_id": incident_id, "error": f"Triage loop error: {str(e)}"},
            )

    return StreamingResponse(
        event_generator(),
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
    session: AsyncSession = Depends(get_db_session),
) -> FeedbackCreateResponse:
    """
    Records engineer feedback (worked, failed, partial).
    Persists feedback to PostgreSQL fix_attempts.
    If outcome is 'failed', retains anti-pattern into Hindsight negative memory (kartly-sre).
    If explicit engineer_preference is provided, retains in engineer-{engineer_id}.
    """
    repo = SQLAlchemyRepository(session)
    persisted_to_db = False
    negative_retained = False
    preference_retained = False
    db_error = None
    hindsight_error = None

    by_engineer_int: Optional[int] = None
    if payload.engineer_id:
        try:
            if payload.engineer_id.isdigit():
                by_engineer_int = int(payload.engineer_id)
            elif payload.engineer_id.startswith("engineer-") and payload.engineer_id.split("-")[1].isdigit():
                by_engineer_int = int(payload.engineer_id.split("-")[1])
        except Exception:
            pass

    # 1. Persist fix attempt in PostgreSQL
    try:
        persisted_to_db = await repo.record_fix_attempt(
            incident_code=incident_id,
            suggestion_id=payload.suggestion_id,
            action=payload.attempted_action or "Remediation attempt",
            outcome=payload.outcome,
            by_engineer=by_engineer_int,
            note=payload.note,
        )
    except Exception as e:
        logger.error(f"Database error persisting fix attempt: {e}")
        db_error = str(e)
        persisted_to_db = False

    # Mirror in ephemeral registry for offline mock fallback
    incident = ACTIVE_INCIDENTS.setdefault(incident_id, {"id": incident_id, "feedback": []})
    incident.setdefault("feedback", []).append({
        "suggestion_id": payload.suggestion_id,
        "outcome": payload.outcome,
        "attempted_action": payload.attempted_action,
        "note": payload.note,
        "engineer_id": payload.engineer_id,
        "timestamp": datetime.now(timezone.utc),
    })

    # 2. Retain organizational fix outcome in kartly-sre (especially failed fixes)
    if payload.outcome == "failed":
        try:
            inc = await repo.get_incident(incident_id) or ACTIVE_INCIDENTS.get(incident_id, {})
            svc = inc.get("service_name", "checkout-api")
            sym = inc.get("symptom", "Service degradation")
            neg_ok = await hindsight_service.remember_fix_outcome(
                service_name=svc,
                incident_signature=sym,
                attempted_action=payload.attempted_action or "Attempted action",
                failure_mode=payload.note or f"Action marked as failed on incident {incident_id}",
                outcome="failed",
            )
            negative_retained = bool(neg_ok)
        except Exception as e:
            logger.error(f"Hindsight negative memory retention failed: {e}")
            hindsight_error = str(e)

    # 3. Retain explicit engineer preference into engineer-{engineer_id}
    # Do not infer a personal preference merely because an engineer selected a particular fix.
    if payload.engineer_preference and payload.engineer_id:
        try:
            pref_ok = await hindsight_service.remember_engineer_preference(
                engineer_id=payload.engineer_id,
                preference=payload.engineer_preference,
                category="workflow",
            )
            preference_retained = bool(pref_ok)
        except Exception as e:
            logger.warning(f"Failed to retain engineer preference: {e}")
            if not hindsight_error:
                hindsight_error = str(e)

    return FeedbackCreateResponse(
        incident_id=incident_id,
        status="recorded",
        negative_memory_retained=negative_retained,
        preference_retained=preference_retained,
        persisted_to_db=persisted_to_db,
        database_error=db_error,
        hindsight_error=hindsight_error,
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
    session: AsyncSession = Depends(get_db_session),
) -> ResolveIncidentResponse:
    """
    Closes the incident, writes postmortem facts to PostgreSQL, and triggers episodic retention
    into Hindsight Cloud organizational memory (kartly-sre).
    """
    repo = SQLAlchemyRepository(session)
    persisted_to_db = False
    episodic_retained = False
    db_error = None
    hindsight_error = None

    # 1. Persist resolution in PostgreSQL
    try:
        persisted_to_db = await repo.resolve_incident(
            incident_code=incident_id,
            root_cause=payload.root_cause,
            fix=payload.fix,
            duration_min=payload.duration_min,
        )
    except Exception as e:
        logger.error(f"Database error resolving incident: {e}")
        db_error = str(e)
        persisted_to_db = False

    # Mirror in ephemeral registry for offline mock fallback
    incident = ACTIVE_INCIDENTS.setdefault(incident_id, {"id": incident_id})
    incident["status"] = "resolved"
    incident["root_cause"] = payload.root_cause
    incident["fix"] = payload.fix
    incident["duration_min"] = payload.duration_min
    incident["resolved_at"] = datetime.now(timezone.utc)

    # 2. Retain postmortem into Hindsight organizational bank (kartly-sre)
    try:
        inc = await repo.get_incident(incident_id) or ACTIVE_INCIDENTS.get(incident_id, {})
        svc = inc.get("service_name", "checkout-api")
        sym = inc.get("symptom", "Service degradation")
        rem_ok = await hindsight_service.remember_incident(
            incident_id=incident_id,
            service_name=svc,
            symptom=sym,
            root_cause=payload.root_cause,
            fix=payload.fix,
            duration_min=payload.duration_min,
        )
        episodic_retained = bool(rem_ok)
    except Exception as e:
        logger.error(f"Hindsight postmortem retention failed: {e}")
        hindsight_error = str(e)

    return ResolveIncidentResponse(
        incident_id=incident_id,
        status="resolved",
        episodic_memory_retained=episodic_retained,
        persisted_to_db=persisted_to_db,
        database_error=db_error,
        hindsight_error=hindsight_error,
    )


@router.get(
    "/{incident_id}/memories",
    response_model=MemoriesResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Memories Used for Incident",
)
async def get_incident_memories(
    incident_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> MemoriesResponse:
    """
    Retrieves positive episodic and negative memory entries cited during triage
    for display in the frontend Memory Panel.
    """
    repo = SQLAlchemyRepository(session)
    inc = await repo.get_incident(incident_id) or ACTIVE_INCIDENTS.get(incident_id, {})
    svc = inc.get("service_name", "checkout-api")
    sym = inc.get("symptom", "Database connection pool exhaustion")

    unified = await hindsight_service.retrieve_unified_memory(service_name=svc, symptom=sym)
    memories = unified.get("memory_hits", [])

    return MemoriesResponse(
        incident_id=incident_id,
        count=len(memories),
        memories=memories,
    )
