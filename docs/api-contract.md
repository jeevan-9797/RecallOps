# RecallOps Frozen API Contract Specification

**Status:** Frozen at H2  
**Base URL:** `http://localhost:8000`  
**Swagger UI:** `/docs`  

---

## REST Endpoints Summary

### 1. Root Liveness & Status
* `GET /health`: Returns service status and integration checks.
* `GET /`: Returns service metadata and docs links.

### 2. Alert Ingestion
* `POST /api/alerts`
  * Request: `{"service_name": "checkout-api", "symptom": "HTTP 500 spike", "severity": "CRITICAL"}`
  * Response (201): `{"incident_id": "INC-2045", "status": "created", "created_at": "..."}`

### 3. SRE Agent Triage (SSE Stream)
* `POST /api/incidents/{incident_id}/triage?memory=on|off`
  * Query Param `memory`: `on` (default, Hindsight dual-memory active) or `off` (naive baseline ablation).
  * Content-Type: `text/event-stream`
  * Event Types:
    * `thought`: `{"step": int, "content": str}`
    * `tool_call`: `{"tool": str, "arguments": dict}`
    * `tool_result`: `{"tool": str, "summary": str}`
    * `memory_hit` / `recalled_memory`: `{"memory_type": str, "incident_id": str, "similarity": float, ...}`
    * `warning`: `{"type": "negative_memory_block", "directive": str}`
    * `suggestion`: `{"incident_id": str, "hypothesis": str, "confidence": float, "recommended_action": str, ...}`
    * `done`: `{"incident_id": str, "status": "completed", "duration_ms": int}`
    * `error`: `{"code": str, "message": str}`

### 4. Engineer Feedback (Human-in-the-Loop)
* `POST /api/incidents/{incident_id}/feedback`
  * Request: `{"suggestion_id": "SUG-902", "outcome": "failed", "attempted_action": "restart", "note": "Wiped cache"}`
  * Response (200): `{"incident_id": "INC-2045", "status": "recorded", "negative_memory_retained": true}`

### 5. Incident Resolution & Postmortem
* `POST /api/incidents/{incident_id}/resolve`
  * Request: `{"root_cause": "Unindexed query", "fix": "Rollback and add index", "duration_min": 14}`
  * Response (200): `{"incident_id": "INC-2045", "status": "resolved", "episodic_memory_retained": true}`

### 6. Incident Memories Feed (Memory Panel)
* `GET /api/incidents/{incident_id}/memories`
  * Response (200): `{"incident_id": "INC-2045", "count": int, "memories": [...]}`

### 7. Learned Patterns (Reflect)
* `GET /api/observations`
  * Response (200): `{"observations": ["..."], "count": int, "source": "hindsight_reflect"}`

### 8. Evaluation Benchmark Metrics
* `GET /api/metrics/learning-curve`
  * Response (200): `{"total_incidents_replayed": 40, "accuracy_memory_off": 0.425, "accuracy_memory_on": 0.950, ...}`
  * Note: Phase 0/1 numbers are synthetic baseline demonstration values.

### 9. One-Click Demo Reset
* `POST /api/demo/reset`
  * Request: `{"seed_days": 180}`
  * Response (200): `{"status": "reset_complete", "services_seeded": 8, "deploys_seeded": 45, "memories_seeded": 32, ...}`
