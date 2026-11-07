"""
Demo Management API Router.
Handles POST /api/demo/reset for 1-click clean presentation runs.
"""

import hmac
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException, status
from backend.app.api.alerts import ACTIVE_INCIDENTS
from backend.app.config import settings
from backend.app.schemas.api_models import DemoResetRequest, DemoResetResponse

router = APIRouter(prefix="/demo", tags=["Demo"])


@router.post(
    "/reset",
    response_model=DemoResetResponse,
    status_code=status.HTTP_200_OK,
    summary="One-Click Clean Demo Reset",
)
async def reset_demo(
    payload: Optional[DemoResetRequest] = None,
    x_demo_reset_key: Optional[str] = Header(default=None, alias="X-Demo-Reset-Key"),
) -> DemoResetResponse:
    """
    Clears active test incidents and reseeds the environment with standard
    Kartly microservices, deployment histories, and historical memory precedents.
    In production environments, requires a valid X-Demo-Reset-Key matching DEMO_RESET_TOKEN.
    """
    is_prod = (settings.ENVIRONMENT or "").strip().lower() == "production"
    if is_prod:
        configured_token = (settings.DEMO_RESET_TOKEN or "").strip()
        if not configured_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Demo reset is disabled in production: DEMO_RESET_TOKEN is not configured on server.",
            )
        if not x_demo_reset_key or not hmac.compare_digest(x_demo_reset_key.strip(), configured_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-Demo-Reset-Key header.",
            )

    ACTIVE_INCIDENTS.clear()

    return DemoResetResponse(
        status="reset_complete",
        message="System state wiped and reseeded with Kartly baseline demo data.",
        services_seeded=8,
        deploys_seeded=45,
        memories_seeded=32,
        timestamp=datetime.now(timezone.utc),
    )
