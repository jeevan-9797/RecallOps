# RecallOps: Agent Tool Contracts & Hand-off Specification

**Author:** Member 4 (AI/ML & Model)  
**Consumer:** Member 1 (Backend / FastAPI Agent Loop)  
**Phase:** Phase 0 (H0-H2 Kickoff) -> Phase 1 Foundation  

---

## 1. Overview

This document specifies the exact function-calling tool contracts and structured response schemas used by the RecallOps autonomous SRE agent. 

Backend engineers can import the pre-compiled tools directly into the Groq / OpenAI completion client using:
```python
import json
from pathlib import Path

# Load clean OpenAI/Groq compatible tools array
with open("eval/hand_off_contract.json", "r", encoding="utf-8") as f:
    incident_tools = json.load(f)

# Pass directly to Groq client
response = client.chat.completions.create(
    model="openai/gpt-oss-120b", # or "qwen/qwen3-32b"
    messages=messages,
    tools=incident_tools,
    tool_choice="auto",
)
```

Alternatively, import the Pydantic models directly:
```python
from backend.app.schemas.agent_tools import (
    RecallSimilarIncidentsInput,
    RecallFailedFixesInput,
    GetRecentDeploysInput,
    GetLogsInput,
    GetServiceOwnerInput,
    PostToBandRoomInput,
    AgentTriageResponse,
    get_openai_tool_definitions,
)
```

---

## 2. Tool Specifications

### Tool 1: `recall_similar_incidents`
* **Purpose:** Queries past resolved incidents matching service name and symptom patterns from Hindsight vector/episodic memory.
* **Arguments:**
  * `service_name` (`string`, required): Name of affected microservice (e.g. `"checkout-api"`).
  * `symptom` (`string`, required): Primary symptom or error pattern (e.g. `"HTTP 500 spike post deploy"`).
  * `limit` (`integer`, optional, default: `3`, range: 1–20): Maximum incidents to retrieve.

### Tool 2: `recall_failed_fixes` (Negative Memory)
* **Purpose:** Retrieves negative-memory records of known failed remediations, anti-patterns, or harmful actions attempted for this incident signature to prevent repeating past mistakes.
* **Arguments:**
  * `service_name` (`string`, required): Name of affected service.
  * `incident_signature` (`string`, required): Error signature, stack trace fingerprint, or incident pattern.

### Tool 3: `get_recent_deploys`
* **Purpose:** Fetches deployment history, commit hashes, authors, and rollout status for a service within a given lookback window.
* **Arguments:**
  * `service_name` (`string`, required): Target service name.
  * `lookback_hours` (`integer`, optional, default: `24`, range: 1–720): Search lookback window in hours.

### Tool 4: `get_logs`
* **Purpose:** Retrieves recent log events, error traces, and runtime telemetry for a specific service and incident.
* **Arguments:**
  * `service_name` (`string`, required): Service identifier.
  * `incident_id` (`string`, required): Identifier of the active incident (e.g. `"INC-2045"`).
  * `limit` (`integer`, optional, default: `50`, range: 1–500): Maximum log entries to return.

### Tool 5: `get_service_owner`
* **Purpose:** Finds the primary on-call engineer, team lead, and escalation contact details for a given service.
* **Arguments:**
  * `service_name` (`string`, required): Name of the service.

### Tool 6: `post_to_band_room`
* **Purpose:** Broadcasts real-time triage updates, incident status, hypotheses, or escalation alerts to the virtual incident command/band room.
* **Arguments:**
  * `incident_id` (`string`, required): Target incident war room / band room identifier.
  * `message` (`string`, required): Markdown-formatted message or structured update.
  * `sender` (`string`, optional, default: `"Triage Agent"`): Display name of the sender.

---

## 3. Structured Agent Output Schema (`AgentTriageResponse`)

When the agent reaches a diagnostic conclusion or recommends remediation, its response must conform to `AgentTriageResponse`:

```json
{
  "incident_id": "INC-2045",
  "hypothesis": "Database connection pool exhaustion caused by unindexed query introduced in release v2.4.1.",
  "confidence": 0.92,
  "cited_incident_ids": ["INC-1987", "INC-1842"],
  "failed_fixes_warning": [
    "Do NOT restart payments-db: failed 2x in Sept and caused cascade outage",
    "Do NOT increase thread pool beyond 200 without buffer pool resizing"
  ],
  "recommended_action": "Rollback payments-service to release v2.4.0 and apply hotfix index on orders.customer_id.",
  "likely_owner": "payments-platform-team (@alice-sre)"
}
```

### Schema Field Constraints:
* `incident_id`: String, min length 1.
* `hypothesis`: String, min length 1.
* `confidence`: Float, range `[0.0, 1.0]`. Calibrated confidence level.
* `cited_incident_ids`: Array of strings (historical incident keys).
* `failed_fixes_warning`: Array of strings (explicit anti-patterns retrieved from negative memory).
* `recommended_action`: String, min length 1.
* `likely_owner`: String, min length 1.
