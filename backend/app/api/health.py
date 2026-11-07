"""
Health and Liveness Check Endpoint.
Factual reporting: Does NOT claim external dependencies are connected unless verified.
"""

from fastapi import APIRouter, Query, status
from backend.app.config import settings
from backend.app.schemas.api_models import HealthCheckResponse
from backend.app.services.hindsight_service import hindsight_service

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Liveness and Integration Readiness",
)
async def get_health(
    probe: bool = Query(default=False, description="Optionally run live cloud liveness probe for Hindsight"),
) -> HealthCheckResponse:
    """
    Returns basic service liveness and current configuration readiness of dependencies.
    Does not falsely claim external services are connected unless a live probe succeeded.
    Distinguishes:
    - API key configured / missing
    - SDK initialized / offline
    - Cloud endpoint reachable / authenticated
    - Offline mock provider active
    """
    if not settings.is_hindsight_ready():
        if probe:
            await hindsight_service.check_cloud_liveness()
        hindsight_status = "offline_mock_active"
    else:
        client = hindsight_service._get_client()
        sdk_initialized = client is not None

        if probe and sdk_initialized:
            liveness = await hindsight_service.check_cloud_liveness()
            st = liveness.get("status")
            if st == "connected":
                hindsight_status = "live_cloud_connected"
            elif st == "unauthenticated":
                hindsight_status = "live_cloud_unauthenticated"
            elif st == "server_error":
                hindsight_status = "live_cloud_server_error"
            else:
                hindsight_status = "live_cloud_unreachable"
        elif hindsight_service._last_liveness:
            cached_st = hindsight_service._last_liveness.get("status")
            hindsight_status = f"live_cloud_{cached_st}" if cached_st else "api_key_configured"
        elif sdk_initialized:
            hindsight_status = "sdk_initialized_ready"
        else:
            hindsight_status = "api_key_configured"

    checks = {
        "groq_llm": "api_key_configured" if settings.is_groq_ready() else "api_key_missing",
        "hindsight_memory": hindsight_status,
        "postgresql": "configured" if settings.DATABASE_URL else "not_configured",
        "supabase": "configured" if settings.is_supabase_ready() else "not_configured",
        "band_multiagent": "mock_adapter_active",
    }

    return HealthCheckResponse(
        status="healthy",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        checks=checks,
    )
