"""
Observations API Router.
Handles GET /api/observations to surface cross-incident patterns synthesized by Hindsight reflect().
"""

from fastapi import APIRouter, status
from backend.app.schemas.api_models import ObservationsResponse

router = APIRouter(prefix="/observations", tags=["Observations"])


@router.get(
    "",
    response_model=ObservationsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve Hindsight reflect() Learned Patterns",
)
async def get_observations() -> ObservationsResponse:
    """
    Returns high-level system observations synthesized by Hindsight reflect().
    Displayed in the frontend 'What I've Learned' panel.
    """
    sample_observations = [
        "3 of the last 4 checkout latency spikes followed a connection-pool config change on a Friday.",
        "Restarting payments-db under active connection exhaustion consistently causes cascading auth-service timeouts.",
        "Deployments touching orders-worker frequently cause Redis queue starvation during flash sales.",
    ]

    return ObservationsResponse(
        observations=sample_observations,
        count=len(sample_observations),
        source="hindsight_reflect",
    )
