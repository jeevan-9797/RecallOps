# RecallOps: Hindsight Memory Bank Specification & Integration Guide

**Owner:** Member 4 (AI/ML & Model)  
**Stakeholders:** Member 1 (Backend), Member 3 (Database / Hindsight Client)  
**Phase:** Phase 1: Foundations (H2–H8)  
**Status:** Approved Specification  

---

## 1. Memory Bank Architecture & Namespaces

RecallOps segregates organizational knowledge from individual engineer personas using distinct Hindsight Cloud bank namespaces:

| Bank Namespace | Scope | Purpose | Context Tags | Retention Trigger |
|---|---|---|---|---|
| **`kartly-sre`** | Shared Organization | Stores institutional incident knowledge, postmortems, and failed remediation attempts. | `incident_postmortem`<br>`fix_outcome` | Post-incident resolution or when a mitigation attempt fails. |
| **`engineer-{engineer_id}`** | Per-Engineer Personal | Stores personal preferences, communication styles, and UI custom presets for an on-call engineer. | `user_preference` | User profile setup or explicit user preference updates in UI. |

*Examples of personal banks:*
- `engineer-priya`: Priya (Lead Kubernetes On-Call)
- `engineer-rahul`: Rahul (Principal Systems Architect)

---

## 2. Standardized Retain Payload Formats

All payloads submitted to Hindsight's retain endpoint (`POST /v1/banks/{bank_id}/memories`) must adhere to the standardized schema defined in `eval/memory_templates.py`.

### 2.1 Incident Postmortem (`kartly-sre`)
* **Context Tag:** `incident_postmortem`
* **Canonical String Format:**
  ```
  [<incident_id>][<service_name>][family: <root_cause_family>] Symptom: <symptom>. Tried: <attempted_fixes_and_outcomes>. Root cause: <root_cause>. Fix: <successful_fix>. Time to resolve: <duration_min> min.
  ```
* **Example:**
  ```text
  [INC-1987][payments-db][family: db_connection_exhaustion] Symptom: HTTP 500 error spike post-deploy and checkout timeouts. Tried: Restarted payments-db pod (FAILED, wiped cache and caused cold-start disk storm). Root cause: Unindexed query in v2.4.1 saturated PgBouncer pool. Fix: Deployed index migration idx_orders_customer_id and bumped pool to 400. Time to resolve: 18 min.
  ```
* **Metadata Object:**
  ```json
  {
    "incident_id": "INC-1987",
    "service_name": "payments-db",
    "root_cause_family": "db_connection_exhaustion",
    "duration_min": 18
  }
  ```

---

### 2.2 Fix Attempts & Negative Memory (`kartly-sre`)
* **Context Tag:** `fix_outcome`
* **Canonical String Format:**
  ```
  [<incident_id>][<service_name>] Action: <action> -> Outcome: <FAILED|WORKED|PARTIAL>. Notes: <notes>
  ```
* **Example (Negative Memory - FAILED):**
  ```text
  [INC-1987][payments-db] Action: kubectl rollout restart deployment/payments-db -> Outcome: FAILED. Notes: Pod restart cleared InnoDB buffer pool; disk I/O saturated at 100% causing cascading checkout-api failure.
  ```
* **Example (Remediation - WORKED):**
  ```text
  [INC-1987][payments-db] Action: psql -c "CREATE INDEX CONCURRENTLY idx_orders_cust ON orders(customer_id);" -> Outcome: WORKED. Notes: Active query runtime dropped from 4200ms to 4ms, pool queue cleared in 30 seconds.
  ```
* **Metadata Object:**
  ```json
  {
    "incident_id": "INC-1987",
    "service_name": "payments-db",
    "action": "kubectl rollout restart deployment/payments-db",
    "outcome": "FAILED",
    "is_negative_memory": true
  }
  ```

---

### 2.3 Engineer Preferences (`engineer-{engineer_id}`)
* **Context Tag:** `user_preference`
* **Canonical String Format:**
  ```
  Engineer prefers <concise|detailed> output. Preference: <preference_string>
  ```
* **Seed Profiles:**
  * **Priya (`engineer-priya`):**
    ```text
    Engineer prefers concise output. Preference: Prefers concise output: provide exact copy-ready kubectl commands only, skip verbose architectural explanations.
    ```
  * **Rahul (`engineer-rahul`):**
    ```text
    Engineer prefers detailed output. Preference: Prefers detailed root-cause analysis and comprehensive step-by-step remediation plans.
    ```

---

## 3. Dual-Bank Recall Strategy for Backend (Member 1)

When an alert triggers agent triage, Backend executes three parallel recall requests as built by `eval/recall_strategy.py`:

```
                           +---------------------------+
                           |  Incoming Incident Alert  |
                           |  (service, symptom, user) |
                           +-------------+-------------+
                                         |
                       build_recall_queries(...)
                                         |
            +----------------------------+----------------------------+
            |                            |                            |
            v                            v                            v
   [Query 1: Incidents]         [Query 2: Negative Fixes]    [Query 3: Preferences]
   Bank: kartly-sre             Bank: kartly-sre             Bank: engineer-{id}
   Context: postmortem          Context: fix_outcome         Context: user_preference
   Budget: mid                  Budget: mid                  Budget: low
            |                            |                            |
            +----------------------------+----------------------------+
                                         |
                                         v
                         Hindsight Cloud Retrieval Hits
                                         |
                    +--------------------+--------------------+
                    |                                         |
                    v                                         v
       [Prompt Assembly / Agent]                   [UI Memory Panel Feed]
   - Citations: [INC-1987]                    - Emits SSE: 'memory_citation'
   - Warnings: failed_fixes_warning           - Emits SSE: 'user_profile_loaded'
   - Style: CLI commands vs deep analysis
```

### Recall Request Dictionary:
```python
from eval.recall_strategy import build_recall_queries

queries = build_recall_queries(
    service_name="payments-db",
    symptom="connection pool exhausted",
    engineer_id="priya",
)
# Returns:
# {
#   "incident_query": {"bank_id": "kartly-sre", "budget": "mid", ...},
#   "failed_fix_query": {"bank_id": "kartly-sre", "budget": "mid", ...},
#   "preference_query": {"bank_id": "engineer-priya", "budget": "low", ...}
# }
```

---

## 4. UI Memory Panel Mapping & SSE Events

Backend's FastAPI SSE stream should forward recall results to the frontend Memory Panel using the following event payload formats:

### Event: `memory_citation`
```json
{
  "event": "memory_citation",
  "data": {
    "bank_id": "kartly-sre",
    "incident_id": "INC-1987",
    "service_name": "payments-db",
    "summary": "Connection pool exhausted by unindexed query",
    "relevance_score": 0.94,
    "cited": true
  }
}
```

### Event: `failed_fix_warning`
```json
{
  "event": "failed_fix_warning",
  "data": {
    "bank_id": "kartly-sre",
    "incident_id": "INC-1987",
    "action": "Restarted payments-db pod",
    "outcome": "FAILED",
    "warning": "Do NOT restart pods: wiped cache and caused cold-start disk storm."
  }
}
```

### Event: `engineer_preference_applied`
```json
{
  "event": "engineer_preference_applied",
  "data": {
    "engineer_id": "priya",
    "style": "concise",
    "directive": "Output format: runnable kubectl commands only."
  }
}
```

---

## 5. Citation Sanitization & Hallucination Prevention

The LLM is prompted to only cite `[INC-xxxx]` IDs from recalled memory. Backend must run `eval.recall_strategy.sanitize_agent_response` prior to returning responses to the frontend:
- Strips any hallucinated IDs that were not present in the Hindsight recall result set.
- Enforces explicit fallback: if no memories matched, `hypothesis` must state `"No historical memory match found."`
