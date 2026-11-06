"""
RecallOps Groq Autonomous SRE Agent.
Implements multi-turn ReAct investigation loop, real tool calling, model failover,
dual Hindsight memory integration, PostgreSQL operational grounding, citation verification,
and structured AgentTriageResponse output.
"""

import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from pydantic import ValidationError

from backend.app.config import settings
from backend.app.db.repository import DatabaseRepositoryInterface
from backend.app.schemas.agent_tools import (
    TOOL_DEFINITIONS,
    AgentTriageResponse,
)
from backend.app.services.hindsight_service import HindsightService, hindsight_service
from backend.app.services.tool_handlers import AgentToolDispatcher
from eval.system_prompts import (
    BASELINE_NAIVE_SRE_PROMPT,
    PRODUCTION_RECALLOPS_SRE_PROMPT,
)

logger = logging.getLogger("recallops.agent")


class GroqAgent:
    """
    Autonomous SRE Triage Agent powered by Groq LLMs.
    Primary reasoning engine: openai/gpt-oss-120b
    Fallback / fast engine: qwen/qwen3-32b
    """

    def __init__(
        self,
        tool_dispatcher: AgentToolDispatcher,
        db_repo: Optional[DatabaseRepositoryInterface] = None,
        hindsight: Optional[HindsightService] = None,
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        max_iterations: int = 6,
    ):
        self.tool_dispatcher = tool_dispatcher
        self.db_repo = db_repo or tool_dispatcher.db_repo
        self.hindsight = hindsight or tool_dispatcher.hindsight or hindsight_service
        self.primary_model = primary_model or settings.PRIMARY_MODEL
        self.fallback_model = fallback_model or settings.SECONDARY_MODEL
        self.max_iterations = max_iterations
        self._client = None

    def _get_client(self):
        """Initializes Groq client if valid API key is present."""
        if self._client is None and settings.is_groq_ready():
            try:
                from groq import Groq
                self._client = Groq(api_key=settings.GROQ_API_KEY)
            except Exception as e:
                logger.warning(f"Could not initialize Groq SDK client: {e}")
                self._client = None
        return self._client

    async def stream_triage_loop(
        self,
        incident_id: str,
        service_name: str,
        symptom: str,
        memory_enabled: bool = True,
        engineer_id: Optional[str] = None,
    ) -> AsyncGenerator[Tuple[str, Dict[str, Any]], None]:
        """
        Executes the ReAct investigation loop yielding real-time SSE events:
        - thought
        - tool_call
        - tool_result
        - memory_hit
        - warning
        - suggestion
        - done
        - error
        """
        # 1. Initial Thought Event
        yield (
            "thought",
            {
                "step": 1,
                "content": f"Alert received for {incident_id} on {service_name}. Loading operational telemetry from PostgreSQL...",
                "memory_enabled": memory_enabled,
            },
        )

        # 2. Load Operational Facts from PostgreSQL
        try:
            owner = await self.db_repo.get_service_owner(service_name)
        except Exception as e:
            logger.warning(f"Could not load service owner: {e}")
            owner = f"{service_name}-squad"

        try:
            deploys = await self.db_repo.get_recent_deploys(service_name, lookback_hours=24)
        except Exception as e:
            logger.warning(f"Could not load recent deploys: {e}")
            deploys = []

        try:
            logs = await self.db_repo.get_logs(service_name, incident_id, limit=20)
        except Exception as e:
            logger.warning(f"Could not load logs: {e}")
            logs = []

        # 3. Dual Memory Retrieval (if Memory is ON)
        unified_memory: Dict[str, Any] = {
            "similar_incidents": [],
            "failed_fixes": [],
            "engineer_preferences": [],
            "memory_hits": [],
        }

        if memory_enabled:
            try:
                unified_memory = await self.hindsight.retrieve_unified_memory(
                    service_name=service_name,
                    symptom=symptom,
                    engineer_id=engineer_id,
                )

                # Emit memory_hit events for every retrieved memory
                for hit in unified_memory.get("memory_hits", []):
                    yield ("memory_hit", hit)

                # Emit negative-memory warnings immediately
                for ff in unified_memory.get("failed_fixes", []):
                    directive = ff.get("warning_directive") or ff.get("failure_mode")
                    yield (
                        "warning",
                        {
                            "type": "negative_memory_block",
                            "service_name": ff.get("service_name", service_name),
                            "directive": directive,
                        },
                    )
            except Exception as e:
                logger.error(f"Hindsight retrieval failed: {e}")
                # Distinguish unavailable memory from no matching memory
                yield (
                    "warning",
                    {
                        "type": "memory_service_degraded",
                        "directive": f"Hindsight memory service temporarily unavailable: {e}",
                    },
                )

        client = self._get_client()

        # If live Groq client is absent, execute deterministic simulated triage
        if not client:
            logger.info(f"[OFFLINE AGENT] Executing simulated investigation for {incident_id}")
            async for evt in self._stream_simulated_triage(
                incident_id=incident_id,
                service_name=service_name,
                symptom=symptom,
                owner=owner,
                deploys=deploys,
                logs=logs,
                unified_memory=unified_memory,
                memory_enabled=memory_enabled,
            ):
                yield evt
            return

        # LIVE GROQ AGENT LOOP
        system_prompt = PRODUCTION_RECALLOPS_SRE_PROMPT if memory_enabled else BASELINE_NAIVE_SRE_PROMPT

        # Build comprehensive operational briefing
        user_prompt_lines = [
            f"CRITICAL INCIDENT ALERT:",
            f"Incident ID: {incident_id}",
            f"Affected Service: {service_name}",
            f"Observed Symptom: {symptom}",
            f"Service Owner: {owner}",
            f"Recent Deploys ({len(deploys)} found): {json.dumps(deploys[:3])}",
            f"Recent Logs ({len(logs)} lines found): {json.dumps(logs[:5])}",
        ]

        if memory_enabled:
            if unified_memory["similar_incidents"]:
                user_prompt_lines.append(
                    f"\nRECALLED ORGANIZATIONAL PRECEDENTS ({len(unified_memory['similar_incidents'])}):\n"
                    f"{json.dumps(unified_memory['similar_incidents'])}"
                )
            if unified_memory["failed_fixes"]:
                user_prompt_lines.append(
                    f"\nCRITICAL NEGATIVE-MEMORY WARNINGS ({len(unified_memory['failed_fixes'])}):\n"
                    f"{json.dumps(unified_memory['failed_fixes'])}\n"
                    f"GUARDRAIL MANDATE: You MUST NOT recommend any action listed under NEGATIVE-MEMORY WARNINGS. "
                    f"If your preliminary reasoning considered any such action, REJECT IT immediately and formulate an alternative hypothesis and action."
                )
            if unified_memory["engineer_preferences"]:
                user_prompt_lines.append(
                    f"\nENGINEER WORKFLOW PREFERENCES ({len(unified_memory['engineer_preferences'])}):\n"
                    f"{json.dumps(unified_memory['engineer_preferences'])}\n"
                    f"NOTE: Personal preferences must never override organizational safety warnings."
                )
        else:
            user_prompt_lines.append(
                "\nPerform telemetry investigation using available operational tools and diagnose the root cause."
            )

        user_prompt = "\n".join(user_prompt_lines)

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # In memory-off mode, omit memory tools from tool definitions
        if memory_enabled:
            active_tools = TOOL_DEFINITIONS
        else:
            active_tools = [
                t for t in TOOL_DEFINITIONS
                if t["function"]["name"] not in ("recall_similar_incidents", "recall_failed_fixes")
            ]

        current_model = self.primary_model
        iteration = 0

        while iteration < self.max_iterations:
            iteration += 1
            completion = None

            try:
                completion = client.chat.completions.create(
                    model=current_model,
                    messages=messages,
                    tools=active_tools if active_tools else None,
                    tool_choice="auto" if active_tools else "none",
                    temperature=0.0,
                )
            except Exception as err:
                logger.warning(f"Model '{current_model}' encountered error: {err}. Attempting fallback...")
                if current_model != self.fallback_model:
                    current_model = self.fallback_model
                    yield (
                        "thought",
                        {
                            "step": iteration,
                            "content": f"Primary model encountered error. Failing over to fallback model '{self.fallback_model}'...",
                        },
                    )
                    try:
                        completion = client.chat.completions.create(
                            model=current_model,
                            messages=messages,
                            tools=active_tools if active_tools else None,
                            tool_choice="auto" if active_tools else "none",
                            temperature=0.0,
                        )
                    except Exception as fallback_err:
                        logger.error(f"Fallback model failed as well: {fallback_err}")
                        break
                else:
                    break

            if not completion or not completion.choices:
                break

            choice = completion.choices[0]
            message = choice.message
            tool_calls = getattr(message, "tool_calls", None)

            # If thought/content is present, stream thought event
            if message.content:
                yield (
                    "thought",
                    {
                        "step": iteration,
                        "content": message.content[:250],
                    },
                )

            # Process tool calls
            if tool_calls:
                messages.append(message)
                for tc in tool_calls:
                    fn_name = tc.function.name
                    raw_args = tc.function.arguments
                    try:
                        parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        parsed_args = {}

                    yield (
                        "tool_call",
                        {
                            "tool": fn_name,
                            "arguments": parsed_args,
                        },
                    )

                    # Execute tool via dispatcher with memory_enabled enforcement
                    tool_output = await self.tool_dispatcher.execute_tool(
                        fn_name,
                        parsed_args,
                        memory_enabled=memory_enabled,
                    )

                    summary_str = (
                        f"Executed {fn_name}: {tool_output.get('count', '')} items"
                        if "count" in tool_output
                        else f"Executed {fn_name}"
                    )
                    yield (
                        "tool_result",
                        {
                            "tool": fn_name,
                            "summary": summary_str,
                            "status": tool_output.get("status", "completed"),
                        },
                    )

                    # If tool returned new memories or warnings, emit them
                    if fn_name == "recall_similar_incidents" and "similar_incidents" in tool_output:
                        for sim in tool_output["similar_incidents"]:
                            yield (
                                "memory_hit",
                                {
                                    "bank_type": "organizational",
                                    "source_incident_id": sim.get("incident_id"),
                                    "timestamp": sim.get("timestamp"),
                                    "memory_type": "episodic_resolution",
                                    "outcome": "worked",
                                    "text": f"Precedent {sim.get('incident_id')}: {sim.get('symptom')}. Fix: {sim.get('successful_fix')}",
                                },
                            )

                    if fn_name == "recall_failed_fixes" and "failed_fixes" in tool_output:
                        for ff in tool_output["failed_fixes"]:
                            yield (
                                "warning",
                                {
                                    "type": "negative_memory_block",
                                    "directive": ff.get("warning_directive") or ff.get("failure_mode"),
                                },
                            )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_output),
                    })
                continue

            # Model produced final diagnosis
            content = message.content or ""
            triage_obj = self._parse_agent_response(content, incident_id, service_name)
            if triage_obj:
                # Step 3 requirement: Validate all cited incident IDs against PostgreSQL
                triage_obj.cited_incident_ids = await self._validate_citations(triage_obj.cited_incident_ids)

                # Ensure negative memory warnings are preserved
                if memory_enabled and unified_memory["failed_fixes"]:
                    for ff in unified_memory["failed_fixes"]:
                        directive = ff.get("warning_directive") or ff.get("failure_mode")
                        if directive and directive not in triage_obj.failed_fixes_warning:
                            triage_obj.failed_fixes_warning.append(directive)

                yield ("suggestion", triage_obj.model_dump())
                yield (
                    "done",
                    {
                        "incident_id": incident_id,
                        "status": "completed",
                        "memory_enabled": memory_enabled,
                        "memory_augmented": memory_enabled,
                        "model_used": current_model,
                        "iterations": iteration,
                    },
                )
                return

        # Fallback if loop exhausted or model failed
        logger.warning(f"ReAct loop exhausted without valid diagnosis. Emitting safe fallback.")
        fallback_resp = await self._build_safe_fallback_response(
            incident_id=incident_id,
            service_name=service_name,
            symptom=symptom,
            owner=owner,
            unified_memory=unified_memory,
            memory_enabled=memory_enabled,
        )
        yield ("suggestion", fallback_resp.model_dump())
        yield (
            "done",
            {
                "incident_id": incident_id,
                "status": "completed",
                "memory_enabled": memory_enabled,
                "memory_augmented": memory_enabled,
                "model_used": "safe_fallback",
            },
        )

    async def run_triage_loop(
        self,
        incident_id: str,
        service_name: str,
        symptom: str,
        memory_enabled: bool = True,
        engineer_id: Optional[str] = None,
    ) -> AgentTriageResponse:
        """Non-streaming convenience wrapper around stream_triage_loop."""
        suggestion_payload: Optional[Dict[str, Any]] = None
        async for event_type, data in self.stream_triage_loop(
            incident_id=incident_id,
            service_name=service_name,
            symptom=symptom,
            memory_enabled=memory_enabled,
            engineer_id=engineer_id,
        ):
            if event_type == "suggestion":
                suggestion_payload = data

        if suggestion_payload:
            return AgentTriageResponse.model_validate(suggestion_payload)

        # Fallback default
        return AgentTriageResponse(
            incident_id=incident_id,
            hypothesis="Investigation completed without conclusive diagnosis.",
            confidence=0.4,
            cited_incident_ids=[],
            failed_fixes_warning=[],
            recommended_action=f"Inspect telemetry and logs for {service_name}.",
            likely_owner=f"{service_name}-squad",
        )

    async def _validate_citations(self, cited_ids: List[str]) -> List[str]:
        """
        Validates that cited incident IDs exist in PostgreSQL to prevent LLM hallucinations.
        Unverified or fabricated incident codes are filtered out.
        """
        valid: List[str] = []
        for cid in cited_ids:
            try:
                exists = await self.db_repo.incident_exists(cid)
                if exists:
                    valid.append(cid)
                else:
                    logger.warning(f"Filtered out unverified/fabricated incident ID citation: '{cid}'")
            except Exception as e:
                logger.error(f"Error verifying cited incident '{cid}' in database: {e}")
        return valid

    def _parse_agent_response(self, text: str, incident_id: str, service_name: str) -> Optional[AgentTriageResponse]:
        """Parses model text into structured AgentTriageResponse contract."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            return AgentTriageResponse.model_validate(data)
        except Exception:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    return AgentTriageResponse.model_validate(data)
                except Exception:
                    pass
        return None

    async def _stream_simulated_triage(
        self,
        incident_id: str,
        service_name: str,
        symptom: str,
        owner: str,
        deploys: List[Dict[str, Any]],
        logs: List[Dict[str, Any]],
        unified_memory: Dict[str, Any],
        memory_enabled: bool,
    ) -> AsyncGenerator[Tuple[str, Dict[str, Any]], None]:
        """Deterministic simulated triage execution for offline testing and mock runs."""
        # Tool: get_logs
        yield (
            "tool_call",
            {"tool": "get_logs", "arguments": {"service_name": service_name, "incident_id": incident_id, "limit": 20}},
        )
        logs_res = await self.tool_dispatcher.execute_tool(
            "get_logs",
            {"service_name": service_name, "incident_id": incident_id, "limit": 20},
            memory_enabled=memory_enabled,
        )
        yield (
            "tool_result",
            {"tool": "get_logs", "summary": f"{logs_res.get('count', 0)} log traces loaded from PostgreSQL"},
        )

        # Tool: get_recent_deploys
        yield (
            "tool_call",
            {"tool": "get_recent_deploys", "arguments": {"service_name": service_name, "lookback_hours": 24}},
        )
        deploys_res = await self.tool_dispatcher.execute_tool(
            "get_recent_deploys",
            {"service_name": service_name, "lookback_hours": 24},
            memory_enabled=memory_enabled,
        )
        yield (
            "tool_result",
            {"tool": "get_recent_deploys", "summary": f"{deploys_res.get('count', 0)} recent deploys retrieved"},
        )

        if memory_enabled:
            # Tool: recall_similar_incidents
            yield (
                "tool_call",
                {"tool": "recall_similar_incidents", "arguments": {"service_name": service_name, "symptom": symptom, "limit": 3}},
            )
            sim_res = await self.tool_dispatcher.execute_tool(
                "recall_similar_incidents",
                {"service_name": service_name, "symptom": symptom, "limit": 3},
                memory_enabled=True,
            )
            yield (
                "tool_result",
                {"tool": "recall_similar_incidents", "summary": f"{sim_res.get('count', 0)} historical precedents found"},
            )

            # Tool: recall_failed_fixes
            yield (
                "tool_call",
                {"tool": "recall_failed_fixes", "arguments": {"service_name": service_name, "incident_signature": symptom}},
            )
            ff_res = await self.tool_dispatcher.execute_tool(
                "recall_failed_fixes",
                {"service_name": service_name, "incident_signature": symptom},
                memory_enabled=True,
            )
            yield (
                "tool_result",
                {"tool": "recall_failed_fixes", "summary": f"{ff_res.get('count', 0)} known failed fixes identified"},
            )

            # Formulate targeted memory-augmented suggestion
            cited = ["INC-1987"]
            valid_cited = await self._validate_citations(cited)
            triage_obj = AgentTriageResponse(
                incident_id=incident_id,
                hypothesis=f"Database connection pool exhaustion caused by unindexed query introduced in recent release on {service_name}.",
                confidence=0.94,
                cited_incident_ids=valid_cited,
                failed_fixes_warning=[
                    "Do NOT restart payments-db: failed 2x in Sept (INC-1987) and caused cascading outage",
                ],
                recommended_action=f"Rollback {service_name} to previous release and apply connection pooler limits.",
                likely_owner=owner or "payments-platform-team (@alice-sre)",
            )
        else:
            # Memory disabled: naive baseline
            triage_obj = AgentTriageResponse(
                incident_id=incident_id,
                hypothesis="Possible thread starvation, CPU congestion, or resource exhaustion.",
                confidence=0.45,
                cited_incident_ids=[],
                failed_fixes_warning=[],
                recommended_action=f"Restart {service_name} pods and scale replica count.",
                likely_owner=owner or "on-call-generalist",
            )

        yield ("suggestion", triage_obj.model_dump())
        yield (
            "done",
            {
                "incident_id": incident_id,
                "status": "completed",
                "memory_enabled": memory_enabled,
                "memory_augmented": memory_enabled,
                "mode": "simulated",
            },
        )

    async def _build_safe_fallback_response(
        self,
        incident_id: str,
        service_name: str,
        symptom: str,
        owner: str,
        unified_memory: Dict[str, Any],
        memory_enabled: bool,
    ) -> AgentTriageResponse:
        """Generates a safe fallback response if LLM completion loop is exhausted."""
        if memory_enabled:
            cited = [inc["incident_id"] for inc in unified_memory.get("similar_incidents", []) if "incident_id" in inc]
            valid_cited = await self._validate_citations(cited)
            warnings = [
                ff.get("warning_directive") or ff.get("failure_mode")
                for ff in unified_memory.get("failed_fixes", [])
                if ff.get("warning_directive") or ff.get("failure_mode")
            ]
            return AgentTriageResponse(
                incident_id=incident_id,
                hypothesis=f"Operational anomaly on {service_name} matching precedent incident signatures.",
                confidence=0.85,
                cited_incident_ids=valid_cited,
                failed_fixes_warning=warnings,
                recommended_action=f"Verify recent deployments and apply connection pool caps on {service_name}.",
                likely_owner=owner,
            )
        else:
            return AgentTriageResponse(
                incident_id=incident_id,
                hypothesis=f"Generic operational degradation observed on {service_name}.",
                confidence=0.45,
                cited_incident_ids=[],
                failed_fixes_warning=[],
                recommended_action=f"Restart {service_name} and monitor health metrics.",
                likely_owner=owner,
            )
