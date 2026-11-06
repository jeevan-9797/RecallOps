"""
Alerts Ingestion API Router.
Handles POST /api/alerts to register an active incident and trigger investigation.
"""

from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, status
from backend.app.schemas.api_models import AlertCreateRequest, AlertCreateResponse

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# Ephemeral in-memory incident registry for P0 development and mock testing
ACTIVE_INCIDENTS: dict[str, dict] = {}


@router.post(
    "",
    response_model=AlertCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Operational Alert",
)
async def create_alert(payload: AlertCreateRequest) -> AlertCreateResponse:
    """
    Ingests an incoming alert from monitoring systems (e.g. Kartly latency spike),
    generates a tracked incident ID, and stores the initial incident state.
    """
    incident_num = 2000 + len(ACTIVE_INCIDENTS) + 1
    incident_id = f"INC-{incident_num}"
    created_at = payload.timestamp or datetime.now(timezone.utc)

    incident_record = {
        "id": incident_id,
        "service_name": payload.service_name,
        "symptom": payload.symptom,
        "severity": payload.severity,
        "status": "created",
        "created_at": created_at,
        "feedback": [],
        "memories": [
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
                "warning_directive": "Do NOT restart payments-db under active connection exhaustion: cold cache will crash downstream checkout flows.",
            },
        ],
    }
    ACTIVE_INCIDENTS[incident_id] = incident_record

    return AlertCreateResponse(
        incident_id=incident_id,
        status="created",
        created_at=created_at,
    )
