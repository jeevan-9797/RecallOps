"""
RecallOps Multi-Bank Recall Pipeline & Hypothesis Ranking (Phase 2)
Author: Member 4 (AI/ML & Model)
Phase: Phase 2: Core Loop (H8–H16)

Implements:
1. Multi-Query Retrieval Pipeline:
   - Query 1: Symptom + service (`kartly-sre`, context: `incident_postmortem`)
   - Query 2: Recent deployment patterns (`kartly-sre`, context: `incident_postmortem`)
   - Query 3: Failed fixes for this signature (`kartly-sre`, context: `fix_outcome`)
   - Query 4: Engineer style preferences (`engineer-{engineer_id}`, context: `user_preference`)
2. Deduplication & Score Merging by Incident ID.
3. Hypothesis Ranking Engine: combines semantic similarity, recency weighting,
   and outcome filtering (penalizing failed remediations and extracting warnings).
4. Standing Operational Directives (Mental Models spike) for hard rules.
5. SSE streaming format generator compatible with Backend (Member 1).
"""

import math
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field, ConfigDict

from eval.memory_templates import (
    SHARED_SRE_BANK,
    CONTEXT_INCIDENT_POSTMORTEM,
    CONTEXT_FIX_OUTCOME,
    CONTEXT_USER_PREFERENCE,
    FixOutcome,
    OutputStyle,
    normalize_engineer_bank_id,
    get_seed_engineer_preference,
)
from eval.recall_strategy import (
    extract_incident_citations,
    validate_citations,
)


# ==============================================================================
# DATA MODELS
# ==============================================================================

class MemoryHit(BaseModel):
    """Normalized memory record retrieved from Hindsight Cloud."""
    model_config = ConfigDict(extra="ignore")

    incident_id: str = Field(..., description="Unique incident identifier (e.g. 'INC-1987')")
    service_name: str = Field(..., description="Service component name")
    root_cause: str = Field(..., description="Diagnosed root cause or failure mode")
    symptom: str = Field(..., description="Symptom pattern observed")
    successful_fix: Optional[str] = Field(None, description="Remediation action if worked")
    failed_actions: List[str] = Field(default_factory=list, description="Remediations that failed")
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Semantic similarity score")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_content: str = Field(default="", description="Original payload text")
    source_queries: List[str] = Field(default_factory=list, description="Which queries found this hit")
    is_negative_memory: bool = Field(default=False, description="Whether this is a failed fix record")
    context: str = Field(default=CONTEXT_INCIDENT_POSTMORTEM)


class StandingDirective(BaseModel):
    """Standing operational rule or mental model constraint."""
    rule_id: str
    service_name: str
    condition: str
    directive: str
    priority: str = "CRITICAL"


class RankedHypothesis(BaseModel):
    """Scored and ranked incident hypothesis produced by the pipeline."""
    model_config = ConfigDict(extra="ignore")

    incident_id: str
    service_name: str
    root_cause: str
    recommended_action: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    similarity_score: float
    recency_score: float
    failed_fixes_warning: List[str] = Field(default_factory=list)
    score_breakdown: Dict[str, float] = Field(default_factory=dict)


class TripartiteRecallResult(BaseModel):
    """Consolidated outcome of the multi-bank recall and ranking process."""
    ranked_hypotheses: List[RankedHypothesis] = Field(default_factory=list)
    failed_fixes_warnings: List[str] = Field(default_factory=list)
    standing_directives: List[str] = Field(default_factory=list)
    engineer_preference: Optional[Dict[str, Any]] = None
    raw_hits: List[MemoryHit] = Field(default_factory=list)
    deduplicated_incident_ids: List[str] = Field(default_factory=list)


# ==============================================================================
# STANDING OPERATIONAL RULES (Lightweight Mental Models Spike)
# ==============================================================================

DEFAULT_STANDING_DIRECTIVES: List[StandingDirective] = [
    StandingDirective(
        rule_id="RULE-PAY-01",
        service_name="payments-db",
        condition="connection saturation or high latency",
        directive="Do NOT restart payments-db under active peak load without enabling connection drain in PgBouncer first.",
        priority="CRITICAL",
    ),
    StandingDirective(
        rule_id="RULE-AUTH-02",
        service_name="auth-service",
        condition="traffic spike or pod scaling",
        directive="Always verify JWT signing key cache synchronization before scaling auth-service replicas.",
        priority="HIGH",
    ),
    StandingDirective(
        rule_id="RULE-INGR-03",
        service_name="ingress-gateway",
        condition="504 gateway timeouts",
        directive="Inspect upstream worker keepalive connection exhaustion before restarting Nginx pods.",
        priority="HIGH",
    ),
]


# ==============================================================================
# TEXT SIMILARITY HELPER
# ==============================================================================

def compute_lexical_semantic_similarity(query_text: str, candidate_text: str) -> float:
    """
    Computes token-overlap Jaccard and containment similarity between query and candidate.
    Used for local scoring and testing when Hindsight vector scores are absent.
    """
    if not query_text or not candidate_text:
        return 0.0

    def tokenize(text: str) -> Set[str]:
        words = re.findall(r"[a-zA-Z0-9_\-\.]+", text.lower())
        # Filter basic stop words
        stops = {"and", "or", "the", "a", "an", "in", "on", "at", "to", "for", "with", "is", "of", "post", "due"}
        return {w for w in words if w not in stops and len(w) > 1}

    q_tokens = tokenize(query_text)
    c_tokens = tokenize(candidate_text)

    if not q_tokens or not c_tokens:
        return 0.0

    intersection = q_tokens.intersection(c_tokens)
    union = q_tokens.union(c_tokens)

    jaccard = len(intersection) / len(union) if union else 0.0
    containment = len(intersection) / len(q_tokens) if q_tokens else 0.0

    # Blended score with higher weight on query containment
    score = (0.35 * jaccard) + (0.65 * containment)
    return round(min(max(score, 0.0), 1.0), 4)


# ==============================================================================
# PIPELINE IMPLEMENTATION
# ==============================================================================

class RecallPipeline:
    """
    End-to-end multi-bank recall pipeline.
    Coordinates query generation, retrieval, deduplication, ranking, and SSE formatting.
    """

    def __init__(
        self,
        memory_store: Optional[List[Dict[str, Any]]] = None,
        standing_directives: Optional[List[StandingDirective]] = None,
        sim_weight: float = 0.70,
        recency_weight: float = 0.30,
        failure_penalty: float = 0.50,
    ):
        """
        Args:
            memory_store: In-memory mock corpus of Hindsight memories (for offline dev/test).
            standing_directives: List of standing operational constraints.
            sim_weight: Weight assigned to semantic similarity (0.0 to 1.0).
            recency_weight: Weight assigned to incident recency (0.0 to 1.0).
            failure_penalty: Score reduction applied to actions with documented failures.
        """
        self.memory_store = memory_store if memory_store is not None else []
        self.standing_directives = standing_directives if standing_directives is not None else DEFAULT_STANDING_DIRECTIVES
        self.sim_weight = sim_weight
        self.recency_weight = recency_weight
        self.failure_penalty = failure_penalty

    def add_memory(self, item: Dict[str, Any]) -> None:
        """Dynamically appends a new memory item to the active memory store."""
        self.memory_store.append(item)

    # --------------------------------------------------------------------------
    # 1. TRIPARTITE RECALL EXECUTION
    # --------------------------------------------------------------------------

    def execute_tripartite_recall(
        self,
        service_name: str,
        symptom: str,
        recent_deploy_diff: str = "",
        engineer_id: str = "default",
        hindsight_client: Optional[Any] = None,
    ) -> TripartiteRecallResult:
        """
        Executes the 3 incident queries on `kartly-sre` and 1 preference query on `engineer-{engineer_id}`.
        Merges and deduplicates hits by incident ID.
        """
        clean_service = service_name.strip()
        clean_symptom = symptom.strip()
        clean_diff = recent_deploy_diff.strip()
        clean_engineer = engineer_id.strip().lower()

        # Define the 3 organizational queries
        query_symptom = f"service: {clean_service} symptom: {clean_symptom} root cause"
        query_deploy = f"deployment diff: {clean_diff} service: {clean_service} regression" if clean_diff else ""
        query_failed = f"FAILED fix attempt anti-pattern warning for {clean_service}: {clean_symptom}"

        raw_hits: List[MemoryHit] = []

        if hindsight_client is not None and hasattr(hindsight_client, "recall"):
            # Production path: invoke live Hindsight client
            raw_hits.extend(self._call_client_query(hindsight_client, SHARED_SRE_BANK, query_symptom, "query_1_symptom"))
            if query_deploy:
                raw_hits.extend(self._call_client_query(hindsight_client, SHARED_SRE_BANK, query_deploy, "query_2_deploy"))
            raw_hits.extend(self._call_client_query(hindsight_client, SHARED_SRE_BANK, query_failed, "query_3_failed_fixes"))
            pref_data = self._call_client_preference(hindsight_client, clean_engineer)
        else:
            # Local / Synthetic path: evaluate against in-memory store
            raw_hits.extend(self._mock_query_store(clean_service, clean_symptom, query_symptom, "query_1_symptom"))
            if query_deploy:
                raw_hits.extend(self._mock_query_store(clean_service, clean_diff, query_deploy, "query_2_deploy"))
            raw_hits.extend(self._mock_query_store(clean_service, clean_symptom, query_failed, "query_3_failed_fixes", is_failed_query=True))
            pref_data = self._resolve_engineer_preference(clean_engineer)

        # Standing Directives Check (Objective 4)
        active_directives = self._check_standing_directives(clean_service, clean_symptom)

        # Deduplicate hits by incident_id
        deduped_hits, all_failed_warnings = self._deduplicate_hits(raw_hits)

        # Rank hypotheses
        current_context = {
            "service_name": clean_service,
            "symptom": clean_symptom,
            "deploy_diff": clean_diff,
        }
        ranked = self.rank_hypotheses(deduped_hits, current_context, all_failed_warnings)

        # Assemble full result
        return TripartiteRecallResult(
            ranked_hypotheses=ranked,
            failed_fixes_warnings=all_failed_warnings,
            standing_directives=active_directives,
            engineer_preference=pref_data,
            raw_hits=deduped_hits,
            deduplicated_incident_ids=[h.incident_id for h in deduped_hits if h.incident_id != "UNKNOWN"],
        )

    # --------------------------------------------------------------------------
    # 2. DEDUPLICATION LOGIC
    # --------------------------------------------------------------------------

    def _deduplicate_hits(self, hits: List[MemoryHit]) -> Tuple[List[MemoryHit], List[str]]:
        """
        Consolidates multiple hits referencing the same incident ID into a single unified record.
        Accumulates all failed action warnings.
        """
        dedup_map: Dict[str, MemoryHit] = {}
        failed_warnings: List[str] = []
        seen_warnings: Set[str] = set()

        for hit in hits:
            # Capture explicit failed warnings
            if hit.is_negative_memory or hit.failed_actions:
                for act in hit.failed_actions:
                    warning_msg = f"Do NOT {act}: failed during prior incident {hit.incident_id}"
                    if warning_msg not in seen_warnings:
                        seen_warnings.add(warning_msg)
                        failed_warnings.append(warning_msg)

            inc_id = hit.incident_id.upper()
            if inc_id not in dedup_map:
                dedup_map[inc_id] = hit
            else:
                existing = dedup_map[inc_id]
                # Merge query sources
                for q in hit.source_queries:
                    if q not in existing.source_queries:
                        existing.source_queries.append(q)
                # Keep highest similarity score
                if hit.similarity_score > existing.similarity_score:
                    existing.similarity_score = hit.similarity_score
                # Merge failed actions
                for fa in hit.failed_actions:
                    if fa not in existing.failed_actions:
                        existing.failed_actions.append(fa)
                # Ensure successful fix is retained if discovered in a different hit
                if not existing.successful_fix and hit.successful_fix:
                    existing.successful_fix = hit.successful_fix

        return list(dedup_map.values()), failed_warnings

    # --------------------------------------------------------------------------
    # 3. RANKING & HYPOTHESIS SCORING ENGINE
    # --------------------------------------------------------------------------

    def rank_hypotheses(
        self,
        recalled_hits: List[MemoryHit],
        current_incident: Dict[str, Any],
        failed_warnings: Optional[List[str]] = None,
    ) -> List[RankedHypothesis]:
        """
        Ranks candidate hypotheses combining:
        - Text / semantic similarity
        - Recency weight
        - Outcome penalty (negative memory)
        """
        if failed_warnings is None:
            failed_warnings = []

        query_signature = f"{current_incident.get('service_name', '')} {current_incident.get('symptom', '')} {current_incident.get('deploy_diff', '')}"
        ranked: List[RankedHypothesis] = []

        # Reference time for recency scoring
        now_dt = datetime.now(timezone.utc)

        for hit in recalled_hits:
            # 1. Similarity score
            if hit.similarity_score > 0.0:
                sim_score = hit.similarity_score
            else:
                sim_score = compute_lexical_semantic_similarity(
                    query_text=query_signature,
                    candidate_text=f"{hit.service_name} {hit.symptom} {hit.root_cause} {hit.raw_content}",
                )

            # 2. Recency score (linear/exponential decay based on timestamp or incident sequence)
            recency_score = self._compute_recency_score(hit.timestamp, hit.incident_id, now_dt)

            # 3. Base combined score
            base_score = (self.sim_weight * sim_score) + (self.recency_weight * recency_score)

            # 4. Failure penalty: if the candidate is ONLY a negative memory attempt with NO fix
            outcome_penalty = 0.0
            if hit.is_negative_memory and not hit.successful_fix:
                outcome_penalty = self.failure_penalty

            final_score = round(max(min(base_score - outcome_penalty, 1.0), 0.0), 4)

            # Determine recommended action
            rec_action = hit.successful_fix or "Investigate root cause according to standard runbook."

            # Collect incident-specific warnings
            warnings = [w for w in failed_warnings if hit.incident_id in w]

            ranked.append(
                RankedHypothesis(
                    incident_id=hit.incident_id,
                    service_name=hit.service_name,
                    root_cause=hit.root_cause,
                    recommended_action=rec_action,
                    confidence_score=final_score,
                    similarity_score=sim_score,
                    recency_score=recency_score,
                    failed_fixes_warning=warnings,
                    score_breakdown={
                        "similarity": sim_score,
                        "recency": recency_score,
                        "penalty": outcome_penalty,
                        "base_score": round(base_score, 4),
                    },
                )
            )

        # Sort descending by final score
        ranked.sort(key=lambda x: x.confidence_score, reverse=True)
        return ranked

    def _compute_recency_score(self, timestamp_str: str, incident_id: str, now_dt: datetime) -> float:
        """Calculates a normalized 0.0-1.0 recency score."""
        try:
            dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            delta_days = max((now_dt - dt).total_seconds() / 86400.0, 0.0)
            # Half-life of 30 days
            return round(math.exp(-delta_days / 30.0), 4)
        except Exception:
            # Fallback to incident sequence number (higher ID = more recent)
            match = re.search(r"\d+", incident_id)
            if match:
                num = int(match.group())
                # Normalize relative to a typical 2000s ID
                return round(min(max(num / 2500.0, 0.5), 1.0), 4)
            return 0.70

    # --------------------------------------------------------------------------
    # 4. STANDING DIRECTIVES CHECK
    # --------------------------------------------------------------------------

    def _check_standing_directives(self, service_name: str, symptom: str) -> List[str]:
        """Scans standing operational rules for matching service conditions."""
        triggered: List[str] = []
        sym_lower = symptom.lower()
        svc_lower = service_name.lower()

        for directive in self.standing_directives:
            if directive.service_name.lower() in svc_lower or svc_lower in directive.service_name.lower():
                # Check condition keywords
                cond_words = [w for w in re.findall(r"\w+", directive.condition.lower()) if len(w) > 3]
                if any(w in sym_lower for w in cond_words) or not cond_words:
                    triggered.append(f"[{directive.rule_id}][{directive.priority}] {directive.directive}")

        return triggered

    # --------------------------------------------------------------------------
    # 5. ENGINEER PREFERENCE RESOLUTION
    # --------------------------------------------------------------------------

    def _resolve_engineer_preference(self, engineer_id: str) -> Dict[str, Any]:
        """Resolves engineer preferences from seeds or defaults."""
        seed = get_seed_engineer_preference(engineer_id)
        if seed:
            style = "concise" if "concise" in seed.content.lower() else "detailed"
            return {
                "engineer_id": engineer_id,
                "style": style,
                "directive": seed.content,
                "bank_id": seed.bank_id,
            }
        return {
            "engineer_id": engineer_id,
            "style": "balanced",
            "directive": "Standard SRE operational breakdown with clear command steps.",
            "bank_id": normalize_engineer_bank_id(engineer_id),
        }

    # --------------------------------------------------------------------------
    # 6. MOCK RETRIEVAL EXECUTION (for testing & local execution)
    # --------------------------------------------------------------------------

    def _mock_query_store(
        self,
        service_name: str,
        query_text: str,
        full_query: str,
        query_label: str,
        is_failed_query: bool = False,
    ) -> List[MemoryHit]:
        """Scans the internal memory_store for matching records."""
        hits: List[MemoryHit] = []
        for item in self.memory_store:
            item_svc = item.get("service_name", "").lower()
            if service_name.lower() not in item_svc and item_svc not in service_name.lower():
                continue

            raw = item.get("raw_content", "") or item.get("symptom", "")
            sim = compute_lexical_semantic_similarity(query_text, raw)

            # If searching for failed fixes, boost or require failed outcome
            is_neg = item.get("is_negative_memory", False) or item.get("outcome") == FixOutcome.FAILED.value
            if is_failed_query:
                if not is_neg:
                    continue
                sim = max(sim, 0.75)  # Boost known negative memory match

            if sim > 0.15 or is_failed_query:
                hits.append(
                    MemoryHit(
                        incident_id=item.get("incident_id", "UNKNOWN"),
                        service_name=item.get("service_name", service_name),
                        root_cause=item.get("root_cause", "Unspecified"),
                        symptom=item.get("symptom", query_text),
                        successful_fix=item.get("successful_fix"),
                        failed_actions=item.get("failed_actions", []),
                        similarity_score=sim,
                        timestamp=item.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        raw_content=raw,
                        source_queries=[query_label],
                        is_negative_memory=is_neg,
                        context=item.get("context", CONTEXT_INCIDENT_POSTMORTEM),
                    )
                )

        # Sort hits by similarity
        hits.sort(key=lambda x: x.similarity_score, reverse=True)
        return hits[:5]

    def _call_client_query(self, client: Any, bank_id: str, query: str, label: str) -> List[MemoryHit]:
        """Stub for live Hindsight client recall integration."""
        try:
            res = client.recall(bank_id=bank_id, query=query, limit=5)
            # Normalize to MemoryHit
            hits: List[MemoryHit] = []
            for item in res:
                content = getattr(item, "content", "")
                inc_id = extract_incident_citations(content)
                inc_key = inc_id[0] if inc_id else "UNKNOWN"
                hits.append(
                    MemoryHit(
                        incident_id=inc_key,
                        service_name=getattr(item, "service_name", "unknown"),
                        root_cause=getattr(item, "root_cause", content),
                        symptom=content,
                        similarity_score=float(getattr(item, "score", 0.8)),
                        raw_content=content,
                        source_queries=[label],
                    )
                )
            return hits
        except Exception:
            return []

    def _call_client_preference(self, client: Any, engineer_id: str) -> Dict[str, Any]:
        """Stub for live Hindsight client user preference recall."""
        bank_id = normalize_engineer_bank_id(engineer_id)
        try:
            res = client.recall(bank_id=bank_id, query="user output preference style", limit=1)
            if res:
                content = getattr(res[0], "content", "")
                style = "concise" if "concise" in content.lower() else "detailed"
                return {"engineer_id": engineer_id, "style": style, "directive": content, "bank_id": bank_id}
        except Exception:
            pass
        return self._resolve_engineer_preference(engineer_id)

    # --------------------------------------------------------------------------
    # 7. SSE STREAMING OUTPUT FORMATTER
    # --------------------------------------------------------------------------

    @staticmethod
    def format_for_sse(result: TripartiteRecallResult) -> Dict[str, List[Dict[str, Any]]]:
        """
        Formats recall results into the exact SSE event structures documented in docs/memory-spec.md:
        - `memory_citation`
        - `failed_fix_warning`
        - `engineer_preference_applied`
        - `standing_directive`
        """
        events: Dict[str, List[Dict[str, Any]]] = {
            "memory_citation": [],
            "failed_fix_warning": [],
            "standing_directive": [],
            "engineer_preference_applied": [],
        }

        # Memory citations
        for hyp in result.ranked_hypotheses:
            events["memory_citation"].append(
                {
                    "event": "memory_citation",
                    "data": {
                        "bank_id": SHARED_SRE_BANK,
                        "incident_id": hyp.incident_id,
                        "service_name": hyp.service_name,
                        "summary": hyp.root_cause,
                        "relevance_score": hyp.confidence_score,
                        "cited": True,
                    },
                }
            )

        # Failed fix warnings
        for warning in result.failed_fixes_warnings:
            events["failed_fix_warning"].append(
                {
                    "event": "failed_fix_warning",
                    "data": {
                        "bank_id": SHARED_SRE_BANK,
                        "warning": warning,
                    },
                }
            )

        # Standing directives
        for directive in result.standing_directives:
            events["standing_directive"].append(
                {
                    "event": "standing_directive",
                    "data": {
                        "bank_id": SHARED_SRE_BANK,
                        "directive": directive,
                    },
                }
            )

        # Engineer preference
        if result.engineer_preference:
            events["engineer_preference_applied"].append(
                {
                    "event": "engineer_preference_applied",
                    "data": result.engineer_preference,
                }
            )

        return events
