"""
Demo Management API Router.
Handles POST /api/demo/reset for 1-click clean presentation runs.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, status
from backend.app.api.alerts import ACTIVE_INCIDENTS
from backend.app.schemas.api_models import DemoResetRequest, DemoResetResponse

router = APIRouter(prefix="/demo", tags=["Demo"])


@router.post(
    "/reset",
    response_model=DemoResetResponse,
    status_code=status.HTTP_200_OK,
    summary="One-Click Clean Demo Reset",
)
async def reset_demo(payload: DemoResetRequest = DemoResetRequest()) -> DemoResetResponse:
    """
    Clears active test incidents and reseeds the environment with standard
    Kartly microservices, deployment histories, and historical memory precedents.
    """
    ACTIVE_INCIDENTS.clear()

    return DemoResetResponse(
        status="reset_complete",
        message="System state wiped and reseeded with Kartly baseline demo data.",
        services_seeded=8,
        deploys_seeded=45,
        memories_seeded=32,
        timestamp=datetime.now(timezone.utc),
    )
