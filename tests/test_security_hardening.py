"""
Unit and Integration Tests for RecallOps Final Security Hardening.
Validates:
1. POST /api/demo/reset security (dev bypass, production DEMO_RESET_TOKEN + X-Demo-Reset-Key header).
2. Database error sanitization in feedback and resolve endpoints (masking passwords, generic messages in prod).
3. Generic 500 exception handler sanitization (empty details in production/non-debug mode).
"""

from unittest.mock import patch, AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.api.incidents import _scrub_credentials, sanitize_db_error
from backend.app.core.exceptions import setup_exception_handlers
from backend.app.main import app


# ==============================================================================
# 1. Demo Reset Security Tests
# ==============================================================================


def test_demo_reset_non_production_allows_request_without_token(client):
    """In development/staging, demo reset should succeed without any header."""
    with patch.object(settings, "ENVIRONMENT", "development"):
        response = client.post("/api/demo/reset")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reset_complete"
        assert "System state wiped" in data["message"]


def test_demo_reset_production_missing_server_token_denies_403(client):
    """In production, if DEMO_RESET_TOKEN is not configured on server, return 403 Forbidden."""
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch.object(settings, "DEMO_RESET_TOKEN", None):
        response = client.post("/api/demo/reset")
        assert response.status_code == 403
        data = response.json()
        assert "DEMO_RESET_TOKEN is not configured" in data["detail"]


def test_demo_reset_production_missing_request_header_denies_401(client):
    """In production with configured token, missing X-Demo-Reset-Key header returns 401."""
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch.object(settings, "DEMO_RESET_TOKEN", "prod-super-secret-token-123"):
        response = client.post("/api/demo/reset")
        assert response.status_code == 401
        data = response.json()
        assert "Invalid or missing X-Demo-Reset-Key header" in data["detail"]
        # Ensure secret token is not exposed
        assert "prod-super-secret-token-123" not in response.text


def test_demo_reset_production_invalid_request_header_denies_401(client):
    """In production with configured token, incorrect X-Demo-Reset-Key header returns 401."""
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch.object(settings, "DEMO_RESET_TOKEN", "prod-super-secret-token-123"):
        response = client.post(
            "/api/demo/reset",
            headers={"X-Demo-Reset-Key": "wrong-token-value"},
        )
        assert response.status_code == 401
        data = response.json()
        assert "Invalid or missing X-Demo-Reset-Key header" in data["detail"]
        assert "prod-super-secret-token-123" not in response.text


def test_demo_reset_production_valid_token_allows_200(client):
    """In production with configured token, matching X-Demo-Reset-Key header succeeds with 200."""
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch.object(settings, "DEMO_RESET_TOKEN", "prod-super-secret-token-123"):
        response = client.post(
            "/api/demo/reset",
            headers={"X-Demo-Reset-Key": "prod-super-secret-token-123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reset_complete"
        assert "prod-super-secret-token-123" not in response.text


# ==============================================================================
# 2. Database Error Sanitization Tests
# ==============================================================================


def test_scrub_credentials_masks_sensitive_passwords():
    raw_error = "Connection to postgresql+asyncpg://postgres:super_secret_password_999@db.supabase.co:5432/postgres failed"
    scrubbed = _scrub_credentials(raw_error)
    assert "super_secret_password_999" not in scrubbed
    assert "postgres:***@db.supabase.co:5432" in scrubbed


def test_sanitize_db_error_production():
    raw_error = Exception("FATAL: password authentication failed for user 'postgres' password='my_secret_pw'")
    with patch.object(settings, "ENVIRONMENT", "production"):
        sanitized = sanitize_db_error(raw_error)
        assert sanitized == "Database operation failed"
        assert "my_secret_pw" not in sanitized


def test_sanitize_db_error_development_masks_passwords():
    raw_error = Exception("postgresql://user:secret123@localhost:5432/testdb unreachable")
    with patch.object(settings, "ENVIRONMENT", "development"):
        sanitized = sanitize_db_error(raw_error)
        assert "secret123" not in sanitized
        assert "user:***@localhost" in sanitized


def test_feedback_endpoint_sanitizes_db_error_in_production(client):
    """When DB persistence fails in production, the response database_error must be sanitized."""
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch("backend.app.db.repository.SQLAlchemyRepository.record_fix_attempt", side_effect=Exception("FATAL: database postgresql://u:pw123@host:5432 down")):
        response = client.post(
            "/api/incidents/INC-2045/feedback",
            json={
                "suggestion_id": "SUG-902",
                "outcome": "worked",
                "attempted_action": "Rolled back revision",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["persisted_to_db"] is False
        assert data["database_error"] == "Database operation failed"
        assert "pw123" not in response.text


def test_resolve_endpoint_sanitizes_db_error_in_production(client):
    """When DB resolution fails in production, the response database_error must be sanitized."""
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch("backend.app.db.repository.SQLAlchemyRepository.resolve_incident", side_effect=Exception("OperationalError: password=secret_token_abc refused")):
        response = client.post(
            "/api/incidents/INC-2045/resolve",
            json={
                "root_cause": "Unindexed query in checkout-api",
                "fix": "Replaced bad migration",
                "duration_min": 15,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["persisted_to_db"] is False
        assert data["database_error"] == "Database operation failed"
        assert "secret_token_abc" not in response.text


# ==============================================================================
# 3. Generic 500 Exception Sanitization Tests
# ==============================================================================


def test_generic_500_handler_sanitizes_in_production():
    """In production, unhandled 500 errors must have empty details dict."""
    test_app = FastAPI()
    setup_exception_handlers(test_app)

    @test_app.get("/trigger-unhandled")
    async def trigger_unhandled():
        raise RuntimeError("Internal secret connection details: key=SECRET_12345")

    test_client = TestClient(test_app, raise_server_exceptions=False)

    with patch.object(settings, "ENVIRONMENT", "production"):
        response = test_client.get("/trigger-unhandled")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert data["error"]["message"] == "An unexpected error occurred during request processing."
        assert data["error"]["details"] == {}
        assert "SECRET_12345" not in response.text


def test_generic_500_handler_shows_diagnostic_details_in_debug_mode():
    """In development with DEBUG_MODE=True, details contains exception type and message."""
    test_app = FastAPI()
    setup_exception_handlers(test_app)

    @test_app.get("/trigger-unhandled")
    async def trigger_unhandled():
        raise ValueError("Diagnostic test error message")

    test_client = TestClient(test_app, raise_server_exceptions=False)

    with patch.object(settings, "ENVIRONMENT", "development"), \
         patch.object(settings, "DEBUG_MODE", True):
        response = test_client.get("/trigger-unhandled")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert data["error"]["details"]["exception_type"] == "ValueError"
        assert data["error"]["details"]["message"] == "Diagnostic test error message"
