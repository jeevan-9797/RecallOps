"""
Separate Live Integration Tests for RecallOps.
Only executes when real live credentials (GROQ_API_KEY, HINDSIGHT_API_KEY, live PostgreSQL)
are injected into the environment. Skips automatically during offline CI / unit testing.
"""

import os
import pytest
from backend.app.config import settings
from backend.app.services.hindsight_service import HindsightService


def is_live_groq_available() -> bool:
    key = os.getenv("GROQ_API_KEY")
    return bool(key and key != "your_groq_api_key_here" and len(key) > 10)


def is_live_hindsight_available() -> bool:
    key = os.getenv("HINDSIGHT_API_KEY")
    return bool(key and key != "your_hindsight_api_key_here" and len(key) > 10)


def is_live_postgres_available() -> bool:
    url = os.getenv("DATABASE_URL")
    return bool(url and "localhost:5432" in url)


@pytest.mark.skipif(not is_live_groq_available(), reason="GROQ_API_KEY not configured for live inference test")
def test_live_groq_completion():
    from groq import Groq
    client = Groq(api_key=settings.GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=settings.SECONDARY_MODEL,
        messages=[{"role": "user", "content": "Respond with the word PONG"}],
        max_tokens=10,
    )
    content = resp.choices[0].message.content or ""
    assert "pong" in content.lower()


@pytest.mark.skipif(not is_live_hindsight_available(), reason="HINDSIGHT_API_KEY not configured for live cloud memory test")
def test_live_hindsight_bank_retention():
    import asyncio
    svc = HindsightService(
        endpoint=settings.HINDSIGHT_ENDPOINT,
        api_key=settings.HINDSIGHT_API_KEY,
        bank_id=settings.HINDSIGHT_BANK_ID,
    )

    async def _test():
        ok = await svc.remember_incident(
            incident_id="INC-LIVE-TEST",
            service_name="checkout-api",
            symptom="Integration test ping",
            root_cause="Automated verification test",
            fix="No action required",
            duration_min=1,
            tags=["integration-test"],
        )
        assert ok is True

    asyncio.run(_test())
