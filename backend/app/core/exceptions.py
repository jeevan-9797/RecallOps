"""
RecallOps Centralized Exception Hierarchy and HTTP Exception Handlers.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from backend.app.config import settings

logger = logging.getLogger("recallops.exceptions")


class RecallOpsException(Exception):
    """Base exception for all domain errors within RecallOps."""
    def __init__(
        self,
        message: str,
        error_code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class IncidentNotFoundError(RecallOpsException):
    def __init__(self, incident_id: str):
        super().__init__(
            message=f"Incident with ID '{incident_id}' was not found.",
            error_code="INCIDENT_NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"incident_id": incident_id},
        )


class ExternalServiceError(RecallOpsException):
    def __init__(self, service: str, message: str):
        super().__init__(
            message=f"External service '{service}' failed: {message}",
            error_code="EXTERNAL_SERVICE_ERROR",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"service": service},
        )


def setup_exception_handlers(app: FastAPI) -> None:
    """Registers standard exception handlers on the FastAPI application."""

    @app.exception_handler(RecallOpsException)
    async def recallops_exception_handler(request: Request, exc: RecallOpsException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Input validation failed on request payload.",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        logger.exception(f"Unhandled server exception during request processing: {exc}")
        is_prod = (settings.ENVIRONMENT or "").strip().lower() == "production"
        if is_prod or not settings.DEBUG_MODE:
            details: Dict[str, Any] = {}
        else:
            details = {"exception_type": type(exc).__name__, "message": str(exc)}

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred during request processing.",
                    "details": details,
                }
            },
        )
