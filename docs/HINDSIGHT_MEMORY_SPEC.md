# Hindsight Cloud Memory Specification & Negative-Memory Logic

**Author:** Member 4 (AI/ML & Model)  
**Phase:** Phase 0 Kickoff -> Phase 1 Foundation  
**System:** RecallOps Incident Cognitive Memory  

---

## 1. Overview & Dual-Memory Architecture

RecallOps utilizes a dual-memory system backed by **Hindsight Cloud**:
1. **Positive / Episodic Memory:** Stores historical resolved incidents, root-cause post-mortems, successful remediation runbooks, and service topology graphs.
2. **Negative Memory (Failed Fixes):** Explicitly indexes attempted fixes that failed, regressed metrics, caused cascade outages, or worsened mean-time-to-recovery (MTTR).

```
               +--------------------------------------+
               |         Incoming Active Incident     |
               +-------------------+------------------+
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
        [Episodic Memory]                  [Negative Memory]
   recall_similar_incidents               recall_failed_fixes
                  |                                 |
                  v                                 v
        "INC-1987 resolved by            "Restarting payments-db
         rolling back v2.4"              wiped cache & escalated"
                  \                                 /
                   \                               /
                    v                             v
           +-----------------------------------------------+
           |       RecallOps Agent Diagnostic Synthesis    |
           |   - Informs hypothesis with positive evidence |
           |   - Blocks anti-patterns with negative warnings|
           +-----------------------------------------------+
```

---

## 2. Retention Schema: Ingesting into Hindsight Cloud

When an incident is resolved, the incident conclusion is ingested into Hindsight Cloud using the following structured schemas:

### A. Positive Episodic Record
```json
{
  "memory_type": "episodic_resolution",
  "incident_id": "INC-1987",
  "service_name": "payments-db",
  "symptom": "FATAL: remaining connection slots are reserved for non-replication superuser connections",
  "root_cause": "Leak in connection pool under high traffic spike during marketing campaign",
  "successful_fix": "Increased max_connections to 400 and deployed PgBouncer pooler",
  "resolver": "database-sre (@charlie)",
  "resolution_time_minutes": 18,
  "timestamp": "2026-09-14T10:15:00Z",
  "tags": ["postgres", "connections", "pgbouncer"]
}
```

### B. Negative-Memory Record (Failed Fix)
```json
{
  "memory_type": "failed_fix",
  "failed_fix_id": "FF-302",
  "incident_id": "INC-1987",
  "service_name": "payments-db",
  "incident_signature": "FATAL: remaining connection slots reserved",
  "attempted_action": "systemctl restart postgresql",
  "failure_mode": "Restart cleared active shared buffer pool, causing 100% cold-cache disk I/O thrashing and cascading timeouts across checkout-api and auth-service.",
  "outcome_rating": "CATASTROPHIC_DEGRADATION",
  "warning_directive": "Do NOT restart payments-db under active connection exhaustion: cold cache will crash downstream checkout flows.",
  "attempted_by": "on-call-junior",
  "timestamp": "2026-09-14T09:42:00Z"
}
```

---

## 3. Negative-Memory Guardrail Logic

### Step 1: Mandatory Pre-Condition
The SRE Agent prompt mandates that `recall_failed_fixes` must be queried before finalizing recommendations.

### Step 2: Signature Normalization
The query uses normalized signatures:
- Error code / exception class: e.g. `ConnectionTimeout`, `OOMKilled`, `DeadlockDetected`.
- Service name and target component.

### Step 3: Synthesis & Warning Emission
When a failed fix matches the active symptom signature:
1. The agent extracts `warning_directive`.
2. It appends the directive to `failed_fixes_warning` in `AgentTriageResponse`.
3. If the agent's preliminary reasoning was considering that exact action, it **must reject it** and formulate an alternative hypothesis and action.

---

## 4. Replay Evaluation & Learning Curve Metrics

To mathematically prove agent memory retention in Phase 2:
1. **Trial 1 (Cold / Naive):** Agent runs without memory. May attempt naive fixes (e.g. naive restarts).
2. **Negative Ingestion:** Record the failure into Negative Memory.
3. **Trial 2 (RecallOps with Hindsight):** Replay identical incident alert.
4. **Verification Metric:** 
   $$\text{Avoidance Rate} = \frac{\text{Negative Fixes Rejected}}{\text{Negative Fixes Re-encountered}} = 100\%$$
   $$\Delta \text{MTTR} = \text{MTTR}_{\text{trial 1}} - \text{MTTR}_{\text{trial 2}} > 0$$
