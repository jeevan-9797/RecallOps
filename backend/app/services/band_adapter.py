"""
Band Multi-Agent Communication Adapter Interface and Implementations.
Provides:
1. BandAdapterInterface: Abstract base class for broadcasting triage updates.
2. MockBandAdapter: In-memory mock adapter for offline testing and local development.
3. IdempotencyCache: In-memory sliding-window deduplication cache.
4. RealBandAdapter: Production outbound REST adapter using the verified Band SDK.
5. get_band_adapter: Factory selecting between RealBandAdapter and MockBandAdapter.
"""

import abc
import asyncio
import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("recallops.band")


class BandAdapterInterface(abc.ABC):
    """Abstract interface for broadcasting triage updates to Band incident rooms."""

    @abc.abstractmethod
    async def post_incident_update(
        self,
        incident_id: str,
        message: str,
        sender: str = "Triage Agent",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Broadcasts an operational message to the specified incident room.
        Returns True on delivery success, False otherwise.
        """
        pass


class MockBandAdapter(BandAdapterInterface):
    """
    Local development and offline mock adapter.
    Logs incident updates to stdout/logging without making external network calls.
    """

    def __init__(self, room_prefix: str = "kartly-war-room"):
        self.room_prefix = room_prefix
        self.messages_posted: List[Dict[str, Any]] = []

    async def post_incident_update(
        self,
        incident_id: str,
        message: str,
        sender: str = "Triage Agent",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        entry = {
            "incident_id": incident_id,
            "sender": sender,
            "message": message,
            "metadata": metadata or {},
        }
        self.messages_posted.append(entry)
        logger.info(
            f"[BAND MOCK ROOM: {self.room_prefix}/{incident_id}] {sender}: {message[:100]}..."
        )
        return True


class IdempotencyCache:
    """
    In-memory sliding-window idempotency cache for Band message deduplication.

    ARCHITECTURAL NOTE ON CROSS-PROCESS DEDUPLICATION:
    This cache operates entirely in-memory within the active Python process.
    In multi-worker production topologies (e.g. Uvicorn with multiple workers or
    horizontally scaled container instances), in-memory idempotency guards against
    duplicate dispatches within the same worker process, but does NOT guarantee
    cross-process deduplication across distinct worker processes. For global
    cross-process deduplication, a centralized distributed store (e.g. Redis
    or PostgreSQL advisory lock/table) would be required.
    """

    def __init__(self, ttl_seconds: float = 600.0):
        self.ttl_seconds = ttl_seconds
        self._entries: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _generate_key(
        self,
        incident_id: str,
        message: str,
        suggestion_id: Optional[str] = None,
    ) -> str:
        raw = f"{incident_id}:{suggestion_id or ''}:{message.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def is_duplicate(
        self,
        incident_id: str,
        message: str,
        suggestion_id: Optional[str] = None,
    ) -> bool:
        """Checks if a message has already been broadcast within the TTL window."""
        key = self._generate_key(incident_id, message, suggestion_id)
        now = time.monotonic()
        async with self._lock:
            self._purge_expired(now)
            return key in self._entries

    async def record(
        self,
        incident_id: str,
        message: str,
        suggestion_id: Optional[str] = None,
    ) -> None:
        """Records a message in the idempotency cache."""
        key = self._generate_key(incident_id, message, suggestion_id)
        now = time.monotonic()
        async with self._lock:
            self._purge_expired(now)
            self._entries[key] = now

    def _purge_expired(self, now: float) -> None:
        expired = [k for k, ts in self._entries.items() if (now - ts) > self.ttl_seconds]
        for k in expired:
            del self._entries[k]

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()


class RealBandAdapter(BandAdapterInterface):
    """
    Production Band Adapter utilizing verified Band SDK (REST-only egress).
    Communicates via Band's REST endpoint without opening competing WebSocket connections.
    Includes:
    - In-memory idempotency deduplication.
    - Bounded retries with exponential backoff on transient errors.
    - Total delivery timeout.
    - Redacted logging (no secrets/API keys in logs).
    - Non-fatal error handling (never crashes callers or SSE streams).
    - Connection health status tracking.
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        api_key: Optional[str] = None,
        default_room_id: Optional[str] = None,
        base_url: Optional[str] = None,
        delivery_timeout: float = 5.0,
        max_retries: int = 2,
        idempotency_ttl_seconds: float = 600.0,
        room_mapping: Optional[Dict[str, str]] = None,
        rest_client: Optional[Any] = None,
    ):
        self.agent_id = agent_id
        self.api_key = api_key
        self.default_room_id = default_room_id
        self.base_url = (base_url or "https://app.band.ai").rstrip("/")
        self.delivery_timeout = delivery_timeout
        self.max_retries = max_retries
        self.room_mapping = room_mapping or {}
        self.idempotency = IdempotencyCache(ttl_seconds=idempotency_ttl_seconds)

        # Connection health state
        self.status = "HEALTHY"
        self.consecutive_failures = 0
        self.last_error: Optional[str] = None

        # Pre-injected or lazily constructed AsyncRestClient
        self._client = rest_client

    def _get_client(self):
        """Initializes AsyncRestClient from Band SDK if not already injected."""
        if self._client is None and self.api_key:
            try:
                from band.client.rest import AsyncRestClient
                self._client = AsyncRestClient(api_key=self.api_key, base_url=self.base_url)
            except Exception as e:
                logger.error(f"Failed to initialize Band AsyncRestClient: {self._sanitize_secret(str(e))}")
                self._client = None
        return self._client

    def resolve_room_id(self, incident_id: str) -> Optional[str]:
        """Resolves target Band chat room ID from mappings, default room, or incident ID."""
        if incident_id in self.room_mapping:
            return self.room_mapping[incident_id]
        if self.default_room_id:
            return self.default_room_id
        # Fallback to incident_id if formatted as room identifier
        if incident_id and (len(incident_id) >= 8 or "-" in incident_id):
            return incident_id
        return None

    @staticmethod
    def _sanitize_secret(text: str) -> str:
        """Redacts Band API keys, Bearer tokens, and sensitive headers from log output."""
        if not text:
            return text
        # Redact Band API keys (band_a_...)
        sanitized = re.sub(r"band_a_[A-Za-z0-9_-]+", "[REDACTED_BAND_KEY]", text)
        # Redact Bearer tokens
        sanitized = re.sub(r"Bearer\s+[A-Za-z0-9_\-\.]+", "Bearer [REDACTED_TOKEN]", sanitized)
        # Redact X-API-Key values
        sanitized = re.sub(r"X-API-Key:\s*[A-Za-z0-9_\-]+", "X-API-Key: [REDACTED]", sanitized)
        return sanitized

    def _format_incident_message(
        self,
        incident_id: str,
        message: str,
        sender: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Formats rich markdown payload for Band war room display if metadata is present,
        otherwise preserves original message.
        """
        meta = metadata or {}
        if not meta:
            return f"**[{sender}] ({incident_id}):** {message}"

        severity = meta.get("severity", "CRITICAL").upper()
        confidence = meta.get("confidence")
        conf_str = f" | **Confidence:** {int(confidence * 100)}%" if confidence is not None else ""
        lines = [
            f"🚨 **[{severity} ALERT] RecallOps Triage Update – {incident_id}**",
            f"**Sender:** {sender}{conf_str}",
            "",
            f"**Diagnosis / Hypothesis:**",
            meta.get("hypothesis", message),
        ]

        warnings = meta.get("failed_fixes_warning", [])
        if warnings:
            lines.append("")
            lines.append("⚠️ **NEGATIVE MEMORY WARNINGS (DO NOT ATTEMPT):**")
            for w in warnings:
                lines.append(f"- {w}")

        citations = meta.get("cited_incident_ids", [])
        if citations:
            lines.append("")
            lines.append(f"📚 **Cited Precedent Incidents:** {', '.join(f'`{c}`' for c in citations)}")

        action = meta.get("recommended_action")
        if action:
            lines.append("")
            lines.append(f"🛠️ **Recommended Action:** {action}")

        owner = meta.get("likely_owner")
        if owner:
            lines.append(f"👤 **Likely Service Owner:** {owner}")

        return "\n".join(lines)

    async def post_incident_update(
        self,
        incident_id: str,
        message: str,
        sender: str = "Triage Agent",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Broadcasts an operational triage message to Band room via AsyncRestClient.
        Enforces idempotency, delivery timeout, bounded retries, and non-fatal failure handling.
        """
        meta = metadata or {}
        suggestion_id = meta.get("suggestion_id")

        # 1. Idempotency Check (in-memory sliding window)
        if await self.idempotency.is_duplicate(incident_id, message, suggestion_id):
            logger.info(
                f"[BAND IDEMPOTENCY] Suppressed duplicate update for {incident_id} "
                f"(suggestion_id={suggestion_id or 'none'})"
            )
            return True

        # 2. Resolve target Band room
        room_id = self.resolve_room_id(incident_id)
        if not room_id:
            logger.warning(
                f"Cannot post Band update: No target room resolved for incident '{incident_id}'. "
                f"Set BAND_DEFAULT_ROOM_ID or room_mapping."
            )
            self.last_error = f"No target room for {incident_id}"
            return False

        # 3. Resolve client
        client = self._get_client()
        if client is None:
            logger.warning("Band AsyncRestClient is not configured or unavailable.")
            self.status = "UNAVAILABLE"
            self.last_error = "AsyncRestClient unavailable"
            return False

        # 4. Build ChatMessageRequest payload
        formatted_content = self._format_incident_message(incident_id, message, sender, metadata)

        try:
            from band.client.rest import ChatMessageRequest, DEFAULT_REQUEST_OPTIONS
            request_payload = ChatMessageRequest(
                content=formatted_content,
                mentions=[],  # Required field on ChatMessageRequest; empty list valid for general war room post
            )
        except Exception as err:
            logger.error(f"Failed to construct Band ChatMessageRequest: {err}")
            self.last_error = str(err)
            return False

        # 5. Attempt Delivery with Bounded Retries & Timeout
        attempt = 0
        backoff = 0.5
        while attempt <= self.max_retries:
            attempt += 1
            try:
                # Total delivery timeout per attempt
                await asyncio.wait_for(
                    client.agent_api_messages.create_agent_chat_message(
                        chat_id=room_id,
                        message=request_payload,
                        request_options=DEFAULT_REQUEST_OPTIONS,
                    ),
                    timeout=self.delivery_timeout,
                )

                # Successful delivery
                await self.idempotency.record(incident_id, message, suggestion_id)
                self.consecutive_failures = 0
                self.status = "HEALTHY"
                self.last_error = None
                logger.info(
                    f"[BAND DISPATCH] Successfully delivered update to room '{room_id}' for {incident_id}"
                )
                return True

            except asyncio.TimeoutError:
                err_msg = f"Delivery timed out after {self.delivery_timeout}s (attempt {attempt}/{self.max_retries + 1})"
                logger.warning(f"[BAND TIMEOUT] {err_msg}")
                self.last_error = err_msg
                if attempt <= self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                continue

            except Exception as e:
                sanitized_err = self._sanitize_secret(str(e))
                status_code = getattr(e, "status_code", None)

                # Fatal non-retryable 4xx client errors (bad auth, room missing, validation)
                if status_code and 400 <= status_code < 500:
                    logger.error(
                        f"[BAND CLIENT ERROR] HTTP {status_code} in room '{room_id}': {sanitized_err}. Not retrying."
                    )
                    self.consecutive_failures += 1
                    self.status = "UNAVAILABLE" if status_code == 401 else "DEGRADED"
                    self.last_error = f"HTTP {status_code}: {sanitized_err}"
                    return False

                # Transient 5xx or connection error: retry
                logger.warning(
                    f"[BAND TRANSIENT ERROR] Attempt {attempt}/{self.max_retries + 1} failed for room '{room_id}': {sanitized_err}"
                )
                self.last_error = sanitized_err
                if attempt <= self.max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                continue

        # Exhausted all attempts
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.status = "DEGRADED"
        logger.error(
            f"[BAND DELIVERY FAILED] Exhausted {self.max_retries + 1} attempts for {incident_id}. "
            f"Last error: {self._sanitize_secret(str(self.last_error))}"
        )
        return False


def get_band_adapter() -> BandAdapterInterface:
    """
    Factory function providing the appropriate Band adapter based on configuration.
    Falls back to MockBandAdapter when credentials are not configured.
    """
    try:
        from backend.app.config import settings
        if settings.is_band_ready():
            return RealBandAdapter(
                agent_id=settings.BAND_AGENT_ID,
                api_key=settings.BAND_API_KEY,
                default_room_id=settings.BAND_DEFAULT_ROOM_ID,
                base_url=settings.BAND_API_BASE_URL,
                delivery_timeout=settings.BAND_DELIVERY_TIMEOUT,
                max_retries=settings.BAND_MAX_RETRIES,
            )
    except Exception as e:
        logger.warning(f"Error initializing RealBandAdapter, falling back to mock: {e}")

    return MockBandAdapter()


# Active adapter singleton
band_adapter: BandAdapterInterface = get_band_adapter()
