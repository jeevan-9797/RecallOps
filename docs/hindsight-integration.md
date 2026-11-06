# RecallOps Hindsight Cloud Integration Guide

**Integration Owner:** Member 1 (Backend Lead) & Member 4 (AI/ML Lead)  
**SDK Package:** `hindsight-client` v1.2.0  
**Default Memory Bank:** `kartly-sre`  
**Endpoint:** `https://api.hindsight.cloud/v1`  

---

## 1. Dual-Memory Conceptual Architecture

RecallOps implements a dual-memory cognitive architecture:

1. **Positive / Episodic Memory:**
   * Retained upon incident resolution (`POST /api/incidents/{id}/resolve`).
   * Contains verified root causes, remediation steps, MTTR duration, and tags.
   * Recalled via `recall_similar_incidents` tool to accelerate hypothesis generation.

2. **Negative Memory (Failed Fixes):**
   * Retained when an engineer marks feedback as `failed` (`POST /api/incidents/{id}/feedback`).
   * Contains the incident signature, attempted command, failure mode, and explicit `warning_directive`.
   * Recalled via `recall_failed_fixes` tool to prevent repeating catastrophic actions.

3. **Reflect Observations:**
   * Fetched via `GET /api/observations`.
   * Surfaces cross-incident patterns synthesized across the memory bank.

---

## 2. Retention Schema & Normalization

### Episodic Resolution Record
```json
{
  "content": "Incident INC-1987 (payments-db): FATAL: connection slots reserved. Root cause: connection leak. Fix: deployed PgBouncer.",
  "context": "episodic_resolution",
  "metadata": {
    "memory_type": "episodic_resolution",
    "incident_id": "INC-1987",
    "service_name": "payments-db",
    "symptom": "connection slots exhausted",
    "root_cause": "connection leak during marketing traffic spike",
    "successful_fix": "Increased max_connections to 400 and deployed PgBouncer pooler cap",
    "duration_min": "18",
    "timestamp": "2026-09-14T10:15:00Z"
  },
  "tags": ["episodic_resolution", "payments-db"]
}
```

### Negative-Memory Record (Failed Remediation)
```json
{
  "content": "[FAILED_FIX] Incident INC-1987 on payments-db: Action 'systemctl restart postgresql'. Warning: Do NOT restart payments-db under active connection exhaustion.",
  "context": "failed_fix",
  "metadata": {
    "memory_type": "failed_fix",
    "incident_id": "INC-1987",
    "service_name": "payments-db",
    "signature": "ConnectionPoolExhausted",
    "attempted_action": "systemctl restart postgresql",
    "failure_mode": "Cleared shared buffer pool, causing 100% disk I/O thrashing",
    "warning_directive": "Do NOT restart payments-db under active connection exhaustion: cold cache will crash downstream checkout flows.",
    "outcome": "failed",
    "timestamp": "2026-09-14T09:42:00Z"
  },
  "tags": ["failed_fix", "payments-db"]
}
```

---

## 3. Handling Unconfigured & Offline Modes
* If `HINDSIGHT_API_KEY` is absent or contains default template strings, `HindsightService` automatically switches to safe offline mock mode.
* The mock mode provides verified Kartly incident precedents (`INC-1987` and `FF-302`), enabling developers and the frontend to build against the API without blockers.
