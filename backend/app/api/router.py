"""
Master API Router for RecallOps.
Aggregates all sub-routers under the /api prefix.
"""

from fastapi import APIRouter
from backend.app.api.alerts import router as alerts_router
from backend.app.api.incidents import router as incidents_router
from backend.app.api.observations import router as observations_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.demo import router as demo_router

api_router = APIRouter(prefix="/api")

api_router.include_router(alerts_router)
api_router.include_router(incidents_router)
api_router.include_router(observations_router)
api_router.include_router(metrics_router)
api_router.include_router(demo_router)
