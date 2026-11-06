"""
Health and Liveness Check Endpoint.
Factual reporting: Does NOT claim external dependencies are connected unless verified.
"""

from fastapi import APIRouter, status
from backend.app.config import settings
from backend.app.schemas.api_models import HealthCheckResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Service Liveness and Integration Readiness",
)
async def get_health() -> HealthCheckResponse:
    """
    Returns basic service liveness and current configuration readiness of dependencies.
    Does not falsely claim external services are connected unless a live probe succeeded.
    """
    checks = {
        "groq_llm": "api_key_configured" if settings.is_groq_ready() else "api_key_missing",
        "hindsight_memory": "api_key_configured" if settings.is_hindsight_ready() else "api_key_missing",
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
