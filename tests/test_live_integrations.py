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
    key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY")
    return bool(key and key != "your_groq_api_key_here" and len(key) > 10)


def is_live_hindsight_available() -> bool:
    if not settings.is_hindsight_ready():
        return False
    key = os.getenv("HINDSIGHT_API_KEY") or settings.HINDSIGHT_API_KEY
    return bool(key and key != "your_hindsight_api_key_here" and len(key) > 10)


def is_live_postgres_available() -> bool:
    url = os.getenv("DATABASE_URL")
    return bool(url and "localhost:5432" in url)


def is_live_band_available() -> bool:
    key = settings.BAND_API_KEY or os.getenv("BAND_API_KEY")
    room = settings.BAND_DEFAULT_ROOM_ID or os.getenv("BAND_DEFAULT_ROOM_ID")
    return bool(key and key.startswith("band_a_") and room)


@pytest.mark.skipif(not is_live_band_available(), reason="BAND_API_KEY and BAND_DEFAULT_ROOM_ID not configured for live Band test")
def test_live_band_message_delivery():
    import asyncio
    from backend.app.services.band_adapter import RealBandAdapter
    adapter = RealBandAdapter(
        agent_id=settings.BAND_AGENT_ID,
        api_key=settings.BAND_API_KEY,
        default_room_id=settings.BAND_DEFAULT_ROOM_ID,
        base_url=settings.BAND_API_BASE_URL,
    )

    async def _test():
        delivered = await adapter.post_incident_update(
            incident_id="INC-P3-LIVE",
            message="RecallOps P3 Live Integration Test – Band REST delivery successful.",
            sender="RecallOps Lead",
            metadata={
                "severity": "CRITICAL",
                "confidence": 0.98,
                "hypothesis": "RecallOps P3 Live Integration Test – Band REST delivery successful.",
                "recommended_action": "Verify message receipt in the Band war room chat channel.",
                "likely_owner": "recallops-backend-lead",
            },
        )
        assert delivered is True

    asyncio.run(_test())


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
