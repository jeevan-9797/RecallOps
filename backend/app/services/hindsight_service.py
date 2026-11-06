"""
Hindsight Cloud Dual-Memory Service Wrapper.
Centralizes all memory operations:
1. Positive / Episodic Memory: retain & recall historically resolved incidents.
2. Negative Memory: retain & recall failed fixes / anti-patterns to prevent repeating mistakes.
3. Reflect: synthesize cross-incident patterns into actionable observations.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from backend.app.config import settings

logger = logging.getLogger("recallops.hindsight")


class HindsightService:
    """
    Interface wrapper around the official hindsight-client SDK.
    Gracefully handles network timeouts, unconfigured credentials, and data normalization.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        bank_id: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.endpoint = endpoint or settings.HINDSIGHT_ENDPOINT
        self.api_key = api_key or settings.HINDSIGHT_API_KEY
        self.bank_id = bank_id or settings.HINDSIGHT_BANK_ID
        self.timeout = timeout
        self._client = None

    def _get_client(self):
        """Lazy client initializer."""
        if self._client is None and self.api_key and not self.api_key.startswith("your_"):
            try:
                from hindsight_client import Hindsight
                self._client = Hindsight(
                    base_url=self.endpoint,
                    api_key=self.api_key,
                    timeout=self.timeout,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize Hindsight client: {e}")
                self._client = None
        return self._client

    async def remember_incident(
        self,
        incident_id: str,
        service_name: str,
        symptom: str,
        root_cause: str,
        fix: str,
        duration_min: int,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Retains a structured episodic postmortem into Hindsight Cloud.
        Does NOT retain raw logs.
        """
        content = (
            f"Incident {incident_id} ({service_name}): {symptom}. "
            f"Root cause: {root_cause}. Resolved by: {fix}. MTTR: {duration_min} minutes."
        )
        metadata = {
            "memory_type": "episodic_resolution",
            "incident_id": str(incident_id),
            "service_name": str(service_name),
            "symptom": str(symptom),
            "root_cause": str(root_cause),
            "successful_fix": str(fix),
            "duration_min": str(duration_min),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        all_tags = list(set(["episodic_resolution", service_name] + (tags or [])))

        client = self._get_client()
        if not client:
            logger.info(f"[MOCK HINDSIGHT RETAIN] Retained episodic postmortem for {incident_id}")
            return True

        try:
            # SDK aretain or retain call
            metadata_str = {k: str(v) for k, v in metadata.items()}
            client.retain(
                bank_id=self.bank_id,
                content=content,
                context="episodic_resolution",
                metadata=metadata_str,
                tags=all_tags,
            )
            return True
        except Exception as e:
            logger.error(f"Hindsight remember_incident failed for {incident_id}: {e}")
            return False

    async def remember_fix_outcome(
        self,
        incident_id: str,
        service_name: str,
        signature: str,
        attempted_action: str,
        outcome: str,
        note: Optional[str] = None,
        failure_mode: Optional[str] = None,
        warning_directive: Optional[str] = None,
    ) -> bool:
        """
        Retains an engineer feedback outcome into Hindsight.
        If outcome is 'failed', tags as negative memory to prevent recurrence.
        """
        is_failed = (outcome.lower() == "failed")
        memory_type = "failed_fix" if is_failed else "successful_fix"

        if is_failed and not warning_directive:
            warning_directive = f"Do NOT attempt '{attempted_action}' on {service_name} under {signature}: {note or failure_mode or 'caused regression'}"

        content = (
            f"[{memory_type.upper()}] Incident {incident_id} on {service_name}: Action '{attempted_action}'. "
            f"Outcome: {outcome}. {f'Warning: {warning_directive}' if is_failed else ''}"
        )
        metadata = {
            "memory_type": memory_type,
            "incident_id": str(incident_id),
            "service_name": str(service_name),
            "signature": str(signature),
            "attempted_action": str(attempted_action),
            "outcome": str(outcome),
            "failure_mode": str(failure_mode or note or ""),
            "warning_directive": str(warning_directive or ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        tags = [memory_type, service_name]

        client = self._get_client()
        if not client:
            logger.info(f"[MOCK HINDSIGHT RETAIN] Retained {memory_type} for {incident_id}")
            return True

        try:
            metadata_str = {k: str(v) for k, v in metadata.items()}
            client.retain(
                bank_id=self.bank_id,
                content=content,
                context=memory_type,
                metadata=metadata_str,
                tags=tags,
            )
            return True
        except Exception as e:
            logger.error(f"Hindsight remember_fix_outcome failed: {e}")
            return False

    async def recall_similar(
        self,
        service_name: str,
        symptom: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Recalls past resolved incidents matching service name and symptom patterns from Hindsight.
        Preserves source incident IDs, similarity, and resolution duration.
        """
        query = f"service: {service_name} symptom: {symptom}"
        client = self._get_client()

        if not client:
            # Baseline mock response for Kartly incidents (e.g. INC-1987)
            if "checkout-api" in service_name or "payments" in service_name or "connection" in symptom.lower():
                return [
                    {
                        "memory_type": "episodic_resolution",
                        "incident_id": "INC-1987",
                        "similarity": 0.94,
                        "relative_time": "6 weeks ago",
                        "service_name": "payments-db",
                        "symptom": "FATAL: remaining connection slots are reserved for non-replication superuser connections",
                        "root_cause": "Unindexed query in orders table during campaign traffic spike",
                        "successful_fix": "Increased max_connections to 400 and deployed PgBouncer pooler cap.",
                        "duration_min": 18,
                        "timestamp": "2026-09-14T10:15:00Z",
                    }
                ]
            return []

        try:
            resp = client.recall(
                bank_id=self.bank_id,
                query=query,
                tags=["episodic_resolution"],
            )
            normalized = []
            results = getattr(resp, "results", []) or []
            for item in results[:limit]:
                meta = getattr(item, "metadata", {}) or {}
                scores = getattr(item, "scores", {}) or {}
                score_val = scores.get("similarity", 0.90) if isinstance(scores, dict) else 0.90

                normalized.append({
                    "memory_type": meta.get("memory_type", "episodic_resolution"),
                    "incident_id": meta.get("incident_id", getattr(item, "id", "INC-UNKNOWN")),
                    "similarity": round(float(score_val), 2),
                    "relative_time": meta.get("timestamp", "past incident"),
                    "service_name": meta.get("service_name", service_name),
                    "symptom": meta.get("symptom", getattr(item, "text", "")),
                    "root_cause": meta.get("root_cause", "Investigated cause"),
                    "successful_fix": meta.get("successful_fix", "Applied remediation"),
                    "duration_min": int(meta.get("duration_min", 20)),
                    "timestamp": meta.get("timestamp", datetime.now(timezone.utc).isoformat()),
                })
            return normalized
        except Exception as e:
            logger.warning(f"Hindsight recall_similar failed: {e}")
            return []

    async def recall_failed_fixes(
        self,
        service_name: str,
        incident_signature: str,
    ) -> List[Dict[str, Any]]:
        """
        Recalls known failed fixes and anti-patterns matching the incident signature.
        """
        query = f"service: {service_name} error: {incident_signature}"
        client = self._get_client()

        if not client:
            # Baseline mock response for failed fix anti-pattern
            if "payments-db" in service_name or "checkout" in service_name or "connection" in incident_signature.lower():
                return [
                    {
                        "memory_type": "failed_fix",
                        "failed_fix_id": "FF-302",
                        "incident_id": "INC-1987",
                        "service_name": "payments-db",
                        "attempted_action": "systemctl restart postgresql",
                        "failure_mode": "Restart cleared active shared buffer pool, causing 100% cold-cache disk I/O thrashing and cascading timeouts across checkout-api.",
                        "warning_directive": "Do NOT restart payments-db under active connection exhaustion: cold cache will crash downstream checkout flows.",
                        "timestamp": "2026-09-14T09:42:00Z",
                    }
                ]
            return []

        try:
            resp = client.recall(
                bank_id=self.bank_id,
                query=query,
                tags=["failed_fix"],
            )
            normalized = []
            results = getattr(resp, "results", []) or []
            for item in results:
                meta = getattr(item, "metadata", {}) or {}
                normalized.append({
                    "memory_type": "failed_fix",
                    "failed_fix_id": meta.get("failed_fix_id", getattr(item, "id", "FF-UNKNOWN")),
                    "incident_id": meta.get("incident_id", "INC-HISTORICAL"),
                    "service_name": meta.get("service_name", service_name),
                    "attempted_action": meta.get("attempted_action", "Operational command"),
                    "failure_mode": meta.get("failure_mode", getattr(item, "text", "")),
                    "warning_directive": meta.get("warning_directive", f"Do not repeat this action on {service_name}"),
                    "timestamp": meta.get("timestamp", datetime.now(timezone.utc).isoformat()),
                })
            return normalized
        except Exception as e:
            logger.warning(f"Hindsight recall_failed_fixes failed: {e}")
            return []

    async def learned_patterns(
        self,
        query: str = "What recurring failure modes, cascading issues, or deployment patterns exist?",
    ) -> List[str]:
        """
        Invokes Hindsight reflect() across the incident memory bank to extract synthesized insights.
        """
        client = self._get_client()
        if not client:
            return [
                "3 of the last 4 checkout latency spikes followed a connection-pool config change on a Friday.",
                "Restarting payments-db under active connection exhaustion consistently causes cascading auth-service timeouts.",
                "Deployments touching orders-worker frequently cause Redis queue starvation during flash sales.",
            ]

        try:
            resp = client.reflect(
                bank_id=self.bank_id,
                query=query,
            )
            text = getattr(resp, "text", "") or ""
            if not text:
                return ["No reflections generated yet for active bank."]

            # Extract distinct lines or bullet points
            lines = [line.strip().lstrip("-*123456789. ") for line in text.split("\n") if line.strip()]
            return lines if lines else [text]
        except Exception as e:
            logger.warning(f"Hindsight learned_patterns failed: {e}")
            return ["Reflect synthesis temporarily unavailable."]


# Global service singleton
hindsight_service = HindsightService()
