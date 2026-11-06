"""
RecallOps Backend Application Entrypoint.
FastAPI foundation for the Autonomous SRE Incident Response Agent.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import settings
from backend.app.core.exceptions import setup_exception_handlers
from backend.app.api.health import router as health_router
from backend.app.api.router import api_router


def create_application() -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    app = FastAPI(
        title="RecallOps Autonomous SRE Agent API",
        description=(
            "AI-powered incident response platform with Hindsight Cloud dual-memory "
            "(positive episodic resolution history + negative memory of failed fixes). "
            "Built for the Hindsight AI Agents Hackathon."
        ),
        version=settings.VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS for Next.js frontend (localhost:3000 and custom origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register centralized exception handlers
    setup_exception_handlers(app)

    # Mount health endpoint at root level
    app.include_router(health_router)

    # Mount frozen API contracts under /api
    app.include_router(api_router)

    @app.get("/", tags=["Root"])
    async def root():
        return JSONResponse(
            content={
                "project": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT,
                "documentation": "/docs",
                "health": "/health",
            }
        )

    return app


app = create_application()
