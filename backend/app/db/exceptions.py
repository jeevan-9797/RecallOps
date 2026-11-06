"""
Database-specific Domain Exceptions.
"""

from typing import Any, Dict, Optional
from backend.app.core.exceptions import RecallOpsException


class DatabaseError(RecallOpsException):
    """Base class for database-related operational errors."""
    def __init__(
        self,
        message: str,
        error_code: str = "DATABASE_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message=message, error_code=error_code, status_code=status_code, details=details)


class DatabaseConnectionError(DatabaseError):
    """Raised when the database engine cannot connect to the PostgreSQL instance."""
    def __init__(self, message: str = "Unable to connect to PostgreSQL database."):
        super().__init__(message=message, error_code="DATABASE_CONNECTION_ERROR", status_code=503)


class RecordNotFoundError(DatabaseError):
    """Raised when a queried entity does not exist in the database."""
    def __init__(self, entity: str, identifier: Any):
        super().__init__(
            message=f"{entity} with identifier '{identifier}' was not found.",
            error_code="RECORD_NOT_FOUND",
            status_code=404,
            details={"entity": entity, "identifier": identifier},
        )


class DatabaseTransactionError(DatabaseError):
    """Raised when a database transaction fails or is aborted."""
    def __init__(self, message: str = "Database transaction failed."):
        super().__init__(message=message, error_code="DATABASE_TRANSACTION_ERROR", status_code=500)
