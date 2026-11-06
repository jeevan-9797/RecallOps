"""
Hindsight Cloud Dual-Memory Service Wrapper.
Supports:
1. Organizational Bank (kartly-sre):
   - Historical incidents, postmortems, successful fixes.
   - Negative memory of failed fixes and catastrophic anti-patterns.
   - Learned patterns via reflect().
2. Engineer Preference Bank (engineer-{engineer_id}):
   - Verified personal troubleshooting preferences, communication styles, explanation depth.
   - Strictly isolated from shared organizational memory.
"""

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional

from backend.app.config import settings

logger = logging.getLogger("recallops.hindsight")


def sanitize_engineer_id(engineer_id: str) -> str:
    """
    Validates and normalizes engineer identifier to prevent arbitrary bank targeting.
    Permits only alphanumeric characters, underscores, and hyphens.
    """
    cleaned = str(engineer_id).strip().lstrip("@").lower()
    if not re.match(r"^[a-z0-9_-]+$", cleaned):
        raise ValueError(
            f"Invalid engineer_id format: '{engineer_id}'. Must contain only alphanumeric characters, hyphens, and underscores."
        )
    return cleaned


class HindsightService:
    """
    Centralized dual-memory interface managing organizational knowledge (kartly-sre)
    and engineer-specific preferences (engineer-{engineer_id}).
    """

    ORGANIZATIONAL_BANK = "kartly-sre"

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        bank_id: Optional[str] = None,
        default_bank_id: Optional[str] = None,
        timeout: float = 10.0,
    ):
        self.endpoint = endpoint or settings.HINDSIGHT_ENDPOINT
        self.api_key = api_key or settings.HINDSIGHT_API_KEY
        self.default_bank_id = bank_id or default_bank_id or self.ORGANIZATIONAL_BANK
        self.timeout = timeout
        self._client = None

        # Known simulated banks for offline/mock test environments
        self._offline_banks: set[str] = {
            self.ORGANIZATIONAL_BANK,
            "engineer-priya",
            "engineer-alice",
            "engineer-aarav",
            "engineer-rahul",
            "engineer-1",
            "engineer-4",
        }
        # Ephemeral offline memory stores for tests
        self._offline_memories: Dict[str, List[Dict[str, Any]]] = {
            self.ORGANIZATIONAL_BANK: [],
            "engineer-priya": [
                {
                    "bank_type": "engineer",
                    "bank_id": "engineer-priya",
                    "memory_type": "engineer_preference",
                    "text": "Prefers immediate root-cause rollbacks before running deep query profile scripts.",
                    "outcome": "preference",
                    "timestamp": "2026-10-12T08:00:00Z",
                }
            ],
            "engineer-aarav": [
                {
                    "bank_type": "engineer",
                    "bank_id": "engineer-aarav",
                    "memory_type": "engineer_preference",
                    "text": "Prefers concise terminal commands and explicit connection pool metrics.",
                    "outcome": "preference",
                    "timestamp": "2026-10-15T09:30:00Z",
                }
            ],
            "engineer-rahul": [
                {
                    "bank_type": "engineer",
                    "bank_id": "engineer-rahul",
                    "memory_type": "engineer_preference",
                    "text": "Prefers step-by-step verification commands and explicit deployment diffs.",
                    "outcome": "preference",
                    "timestamp": "2026-10-18T11:00:00Z",
                }
            ],
        }

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
                logger.warning(f"Failed to initialize live Hindsight client: {e}")
                self._client = None
        return self._client

    def bank_exists(self, bank_id: str) -> bool:
        """
        Validates whether the specified bank exists in Hindsight.
        Never silently substitutes kartly-sre if an engineer bank is missing.
        """
        client = self._get_client()
        if client:
            try:
                cfg = client.get_bank_config(bank_id)
                return bool(cfg)
            except Exception:
                return False
        # Offline mode
        return bank_id in self._offline_banks

    async def remember_incident(
        self,
        incident_id: str,
        service_name: str,
        symptom: str,
        root_cause: str,
        fix: str,
        duration_min: int,
        tags: Optional[List[str]] = None,
        bank_id: Optional[str] = None,
    ) -> bool:
        """
        Retains an operational postmortem into organizational memory (kartly-sre).
        Does NOT retain raw logs.
        """
        target_bank = bank_id or self.ORGANIZATIONAL_BANK
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
            logger.info(f"[OFFLINE HINDSIGHT RETAIN] Retained postmortem for {incident_id} into {target_bank}")
            self._offline_memories.setdefault(target_bank, []).append({
                "bank_type": "organizational",
                "bank_id": target_bank,
                "memory_type": "episodic_resolution",
                "source_incident_id": incident_id,
                "text": content,
                "outcome": "worked",
                "timestamp": metadata["timestamp"],
            })
            return True

        try:
            metadata_str = {k: str(v) for k, v in metadata.items()}
            client.retain(
                bank_id=target_bank,
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
        incident_id: Optional[str] = None,
        service_name: Optional[str] = None,
        signature: Optional[str] = None,
        attempted_action: Optional[str] = None,
        outcome: str = "failed",
        incident_signature: Optional[str] = None,
        note: Optional[str] = None,
        failure_mode: Optional[str] = None,
        warning_directive: Optional[str] = None,
        bank_id: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """
        Retains a fix attempt outcome into organizational memory (kartly-sre).
        If outcome is 'failed', marks as negative memory with an explicit warning.
        """
        target_bank = bank_id or self.ORGANIZATIONAL_BANK
        target_incident_id = incident_id or kwargs.get("incident_code") or "INC-HISTORICAL"
        target_service = service_name or kwargs.get("service") or "checkout-api"
        target_signature = signature or incident_signature or kwargs.get("symptom") or "Service degradation"
        target_action = attempted_action or kwargs.get("action") or "Remediation command"
        is_failed = (outcome.lower() == "failed")
        memory_type = "failed_fix" if is_failed else "successful_fix"

        if is_failed and not warning_directive:
            warning_directive = f"Do NOT attempt '{target_action}' on {target_service} under {target_signature}: {note or failure_mode or 'caused cascading degradation'}"

        content = (
            f"[{memory_type.upper()}] Incident {target_incident_id} on {target_service}: Action '{target_action}'. "
            f"Outcome: {outcome}. {f'Warning: {warning_directive}' if is_failed else ''}"
        )
        metadata = {
            "memory_type": memory_type,
            "incident_id": str(target_incident_id),
            "service_name": str(target_service),
            "signature": str(target_signature),
            "attempted_action": str(target_action),
            "outcome": str(outcome),
            "failure_mode": str(failure_mode or note or ""),
            "warning_directive": str(warning_directive or ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        tags = [memory_type, target_service]

        client = self._get_client()
        if not client:
            logger.info(f"[OFFLINE HINDSIGHT RETAIN] Retained {memory_type} for {incident_id} into {target_bank}")
            self._offline_memories.setdefault(target_bank, []).append({
                "bank_type": "organizational",
                "bank_id": target_bank,
                "memory_type": memory_type,
                "source_incident_id": incident_id,
                "text": content,
                "outcome": outcome,
                "warning_directive": warning_directive,
                "timestamp": metadata["timestamp"],
            })
            return True

        try:
            metadata_str = {k: str(v) for k, v in metadata.items()}
            client.retain(
                bank_id=target_bank,
                content=content,
                context=memory_type,
                metadata=metadata_str,
                tags=tags,
            )
            return True
        except Exception as e:
            logger.error(f"Hindsight remember_fix_outcome failed: {e}")
            return False

    async def remember_engineer_preference(
        self,
        engineer_id: str,
        preference_text: Optional[str] = None,
        preference: Optional[str] = None,
        category: str = "workflow",
        **kwargs: Any,
    ) -> bool:
        """
        Retains an explicit engineer preference into their isolated personal bank (engineer-{engineer_id}).
        Strict Invariants:
        - Never mixes personal preferences into kartly-sre.
        - Only retains genuine, explicitly provided preference text.
        - Validates engineer_id format.
        """
        text = preference_text or preference or kwargs.get("text") or ""
        clean_id = sanitize_engineer_id(engineer_id)
        target_bank = f"engineer-{clean_id}"

        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "memory_type": "engineer_preference",
            "engineer_id": clean_id,
            "category": str(category),
            "timestamp": now,
        }

        client = self._get_client()
        if not client:
            self._offline_banks.add(target_bank)
            self._offline_memories.setdefault(target_bank, []).append({
                "bank_type": "engineer",
                "bank_id": target_bank,
                "memory_type": "engineer_preference",
                "text": text,
                "outcome": "preference",
                "timestamp": now,
            })
            logger.info(f"[OFFLINE HINDSIGHT RETAIN] Retained preference for {clean_id} into {target_bank}")
            return True

        try:
            client.retain(
                bank_id=target_bank,
                content=text,
                context="engineer_preference",
                metadata=metadata,
                tags=["engineer_preference", clean_id, category],
            )
            return True
        except Exception as e:
            logger.error(f"Hindsight remember_engineer_preference failed for {clean_id}: {e}")
            return False

    async def recall_similar(
        self,
        service_name: str,
        symptom: str,
        limit: int = 3,
        bank_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recalls past resolved incidents matching service name and symptom patterns from Hindsight.
        Defaults to organizational bank kartly-sre.
        """
        target_bank = bank_id or self.ORGANIZATIONAL_BANK
        query = f"service: {service_name} symptom: {symptom}"
        client = self._get_client()

        if not client:
            # Baseline mock response for Kartly incidents (e.g. INC-1987)
            if "checkout-api" in service_name or "payments" in service_name or "connection" in symptom.lower():
                return [
                    {
                        "bank_type": "organizational",
                        "bank_id": target_bank,
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
                bank_id=target_bank,
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
                    "bank_type": "organizational",
                    "bank_id": target_bank,
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
            logger.warning(f"Hindsight recall_similar failed for bank {target_bank}: {e}")
            return []

    async def recall_failed_fixes(
        self,
        service_name: str,
        incident_signature: str,
        bank_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recalls known failed fixes and anti-patterns matching the incident signature from organizational memory.
        """
        target_bank = bank_id or self.ORGANIZATIONAL_BANK
        query = f"service: {service_name} error: {incident_signature}"
        client = self._get_client()

        if not client:
            # Baseline mock response for failed fix anti-pattern
            if "payments-db" in service_name or "checkout" in service_name or "connection" in incident_signature.lower():
                return [
                    {
                        "bank_type": "organizational",
                        "bank_id": target_bank,
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
                bank_id=target_bank,
                query=query,
                tags=["failed_fix"],
            )
            normalized = []
            results = getattr(resp, "results", []) or []
            for item in results:
                meta = getattr(item, "metadata", {}) or {}
                normalized.append({
                    "bank_type": "organizational",
                    "bank_id": target_bank,
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

    async def recall_engineer_preferences(
        self,
        engineer_id: str,
        context: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recalls verified personal troubleshooting preferences from engineer-{engineer_id}.
        Invariants:
        - Validates engineer_id format.
        - Verifies bank exists.
        - Never silently substitutes kartly-sre if engineer bank is missing.
        """
        try:
            clean_id = sanitize_engineer_id(engineer_id)
        except ValueError as err:
            logger.warning(f"Rejected invalid engineer_id for preference recall: {err}")
            return []

        target_bank = f"engineer-{clean_id}"

        # Invariant 4 & 5: Check bank existence; never substitute kartly-sre
        if not self.bank_exists(target_bank):
            logger.info(f"Engineer preference bank '{target_bank}' does not exist. Returning empty preferences.")
            return []

        client = self._get_client()
        if not client:
            return self._offline_memories.get(target_bank, [])

        try:
            query = context or "troubleshooting workflow, communication style, diagnostic preferences"
            resp = client.recall(
                bank_id=target_bank,
                query=query,
                tags=["engineer_preference"],
            )
            normalized = []
            for item in getattr(resp, "results", []) or []:
                meta = getattr(item, "metadata", {}) or {}
                normalized.append({
                    "bank_type": "engineer",
                    "bank_id": target_bank,
                    "memory_type": "engineer_preference",
                    "text": getattr(item, "text", ""),
                    "category": meta.get("category", "workflow"),
                    "timestamp": meta.get("timestamp", datetime.now(timezone.utc).isoformat()),
                })
            return normalized
        except Exception as e:
            logger.warning(f"Failed to recall preferences from '{target_bank}': {e}")
            return []

    async def retrieve_unified_memory(
        self,
        service_name: str,
        symptom: str,
        engineer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Unified cognitive memory retrieval pipeline:
        1. Queries organizational bank (kartly-sre) for similar incidents.
        2. Queries organizational bank (kartly-sre) for failed fix warnings.
        3. If engineer_id is available and bank exists, queries engineer-{engineer_id}.
        4. Synthesizes standardized memory_hits list for SSE and frontend panels.

        Safety Priority:
        Organizational safety warnings take absolute precedence over engineer preferences.
        """
        # 1 & 2. Organizational Memory Retrieval
        similar = await self.recall_similar(service_name=service_name, symptom=symptom)
        failed = await self.recall_failed_fixes(service_name=service_name, incident_signature=symptom)

        # 3. Engineer Preferences Retrieval (Optional)
        preferences = []
        if engineer_id:
            preferences = await self.recall_engineer_preferences(engineer_id=engineer_id)

        # 4. Standardized memory_hits for SSE and Memory Panel
        memory_hits: List[Dict[str, Any]] = []

        for inc in similar:
            memory_hits.append({
                "bank_type": "organizational",
                "bank_id": inc.get("bank_id", self.ORGANIZATIONAL_BANK),
                "source_incident_id": inc.get("incident_id"),
                "timestamp": inc.get("timestamp"),
                "memory_type": "episodic_resolution",
                "outcome": "worked",
                "text": f"Precedent {inc.get('incident_id')}: {inc.get('symptom')}. Fix: {inc.get('successful_fix')}",
            })

        for ff in failed:
            memory_hits.append({
                "bank_type": "organizational",
                "bank_id": ff.get("bank_id", self.ORGANIZATIONAL_BANK),
                "source_incident_id": ff.get("incident_id"),
                "timestamp": ff.get("timestamp"),
                "memory_type": "failed_fix",
                "outcome": "failed",
                "text": ff.get("warning_directive") or ff.get("failure_mode") or "Known failed remediation",
            })

        for pref in preferences:
            memory_hits.append({
                "bank_type": "engineer",
                "bank_id": pref.get("bank_id"),
                "source_incident_id": None,
                "timestamp": pref.get("timestamp"),
                "memory_type": "engineer_preference",
                "outcome": "preference",
                "text": pref.get("text"),
            })

        return {
            "similar_incidents": similar,
            "failed_fixes": failed,
            "engineer_preferences": preferences,
            "memory_hits": memory_hits,
        }

    async def learned_patterns(
        self,
        query: str = "What recurring failure modes, cascading issues, or deployment patterns exist?",
        bank_id: Optional[str] = None,
    ) -> List[str]:
        """
        Invokes Hindsight reflect() across organizational memory to extract synthesized observations.
        """
        target_bank = bank_id or self.ORGANIZATIONAL_BANK
        client = self._get_client()

        if not client:
            return [
                "3 of the last 4 checkout latency spikes followed a connection-pool config change on a Friday.",
                "Restarting payments-db under active connection exhaustion consistently causes cascading auth-service timeouts.",
                "Deployments touching orders-worker frequently cause Redis queue starvation during flash sales.",
            ]

        try:
            resp = client.reflect(
                bank_id=target_bank,
                query=query,
            )
            text = getattr(resp, "text", "") or ""
            if not text:
                return ["No reflections generated yet for active bank."]

            lines = [line.strip().lstrip("-*123456789. ") for line in text.split("\n") if line.strip()]
            return lines if lines else [text]
        except Exception as e:
            logger.warning(f"Hindsight learned_patterns failed: {e}")
            return ["Reflect synthesis temporarily unavailable."]


# Global service singleton
hindsight_service = HindsightService()
