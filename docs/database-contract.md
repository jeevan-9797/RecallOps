# RecallOps — Master Database Integration Contract
**Author:** Member 3 (Database & Data Engineering)  
**Target Roles:** Member 1 (Backend), Member 2 (Frontend), Member 4 (AI/ML), Member 5 (Research)  
**Version:** 1.0.0  
**Status:** PROVISIONAL — Ready for Team Agreement

---

## 1. Executive Summary

This document establishes the provisional database schema, data models, table relationships, and API data contracts for **RecallOps**. It enables Member 1 (Backend), Member 2 (Frontend), and Member 4 (AI/ML) to build against a concrete, validated, and reproducible data store without waiting or causing integration friction.

All tables are implemented in PostgreSQL (`database/schema.sql`), with SQLAlchemy 2.0 ORM models (`database/models.py`) and Alembic migrations (`database/migrations/`).

---

## 2. Table Contracts & Specifications

### Table 1: `engineers`
Stores Kartly engineering personnel with ownership and Slack routing.

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Engineer identifier (1–8) |
| `name` | `VARCHAR(128)` | NOT NULL | Engineer full name |
| `team` | `VARCHAR(64)` | NOT NULL | Team name (e.g. "Platform SRE") |
| `slack_handle` | `VARCHAR(64)` | UNIQUE, NOT NULL | Slack username (e.g. `@aarav.sharma`) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Record creation timestamp |

### Table 2: `services`
Stores the 6 microservices comprising Kartly's core architecture.

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Service identifier (1–6) |
| `name` | `VARCHAR(64)` | UNIQUE, NOT NULL | Service DNS name (e.g. `checkout-api`) |
| `team` | `VARCHAR(64)` | NOT NULL | Owning engineering squad |
| `owner_id` | `INTEGER` | FK `engineers.id`, NULLABLE | Primary SRE / Tech Lead owner |
| `tier` | `VARCHAR(16)` | NOT NULL, DEFAULT 'Tier-1' | Service criticality (`Tier-1`, `Tier-2`) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Record creation timestamp |

### Table 3: `deploys`
Stores operational deployment history (~400 records across 6 months).

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Deploy record identifier |
| `service_id` | `INTEGER` | FK `services.id`, NOT NULL | Targeted microservice |
| `author_id` | `INTEGER` | FK `engineers.id`, NULLABLE | Deploying engineer |
| `deployed_at` | `TIMESTAMPTZ` | NOT NULL, INDEXED | Timestamp of deployment event |
| `summary` | `TEXT` | NOT NULL | Git commit message / release summary |
| `config_change` | `BOOLEAN` | NOT NULL, DEFAULT FALSE | Whether config/env vars were modified |
| `diff_note` | `TEXT` | NULLABLE | Key diff lines or configuration change note |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Record creation timestamp |

### Table 4: `alerts`
Stores monitoring threshold breaches that trigger operational incidents.

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Alert event identifier |
| `service_id` | `INTEGER` | FK `services.id`, NOT NULL | Impacted microservice |
| `metric` | `VARCHAR(128)` | NOT NULL, INDEXED | Metric identifier (e.g. `db_connection_pool_active_ratio`) |
| `threshold` | `DOUBLE PRECISION`| NOT NULL | Alert trigger threshold (e.g. `0.90`) |
| `value` | `DOUBLE PRECISION`| NOT NULL | Observed breach value (e.g. `0.985`) |
| `fired_at` | `TIMESTAMPTZ` | NOT NULL, INDEXED | Timestamp when threshold fired |
| `payload` | `JSONB` | NOT NULL, DEFAULT `{}` | Structured contextual metadata (pod, shard, region) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Record creation timestamp |

### Table 5: `incidents`
Master table for 110 operational incidents (INC-0001 to INC-0110).

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Internal incident record ID (1–110) |
| `code` | `VARCHAR(32)` | UNIQUE, NOT NULL | Public incident code (`INC-0001` .. `INC-0110`) |
| `alert_id` | `INTEGER` | FK `alerts.id`, NULLABLE | Associated triggering alert |
| `severity` | `VARCHAR(16)` | NOT NULL, CHECK IN ('P1','P2','P3','P4') | Severity level |
| `status` | `VARCHAR(32)` | NOT NULL, CHECK IN ('OPEN','INVESTIGATING','MITIGATED','RESOLVED') | Lifecycle status |
| `opened_at` | `TIMESTAMPTZ` | NOT NULL, INDEXED | Time incident opened |
| `resolved_at` | `TIMESTAMPTZ` | NULLABLE | Time incident marked resolved |
| `root_cause` | `TEXT` | NOT NULL | Ground-truth root cause summary |
| `root_cause_family`| `VARCHAR(64)` | NOT NULL, INDEXED | Standardized family key (e.g. `db_pool`) |
| `duration_min` | `INTEGER` | NULLABLE | Incident duration in minutes |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Record creation timestamp |

### Table 6: `log_lines`
Stores detailed, authentic operational logs (20–50 logs per incident). **NEVER stored in Hindsight.**

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Log line identifier |
| `incident_id` | `INTEGER` | FK `incidents.id` ON DELETE CASCADE | Associated incident |
| `ts` | `TIMESTAMPTZ` | NOT NULL, INDEXED | Log event timestamp |
| `level` | `VARCHAR(16)` | NOT NULL, CHECK IN ('DEBUG','INFO','WARN','ERROR','FATAL') | Severity |
| `source` | `VARCHAR(64)` | NOT NULL | Component logger (e.g. `HikariCP`, `NginxIngress`) |
| `message` | `TEXT` | NOT NULL | Authentic log message or stack trace |

### Table 7: `fix_attempts`
Chronicles all remediation actions taken by engineers.

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Fix attempt identifier |
| `incident_id` | `INTEGER` | FK `incidents.id` ON DELETE CASCADE | Target incident |
| `action` | `TEXT` | NOT NULL | Remediation command or action description |
| `outcome` | `VARCHAR(32)` | NOT NULL, CHECK IN ('worked','failed','partial') | Result of attempt |
| `by_engineer` | `INTEGER` | FK `engineers.id`, NULLABLE | Engineer executing action |
| `at` | `TIMESTAMPTZ` | NOT NULL | Timestamp when fix was attempted |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Record creation timestamp |

### Table 8: `agent_suggestions`
Stores AI Agent hypotheses generated during triage.

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Suggestion identifier |
| `incident_id` | `INTEGER` | FK `incidents.id` ON DELETE CASCADE | Target incident |
| `hypothesis` | `TEXT` | NOT NULL | Root-cause hypothesis generated by Agent |
| `rank` | `INTEGER` | NOT NULL, CHECK (`rank >= 1`) | Recommendation rank (1, 2, 3) |
| `memory_on` | `BOOLEAN` | NOT NULL, DEFAULT TRUE | Whether Hindsight memory was enabled |
| `accepted` | `BOOLEAN` | NULLABLE | Feedback from engineer (True/False/None) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Timestamp created |

### Table 9: `replay_results`
Stores automated replay evaluation metrics for AI/ML benchmarking.

| Field | Type | Modifiers | Description |
|---|---|---|---|
| `id` | `INTEGER` | PRIMARY KEY, SERIAL | Replay run result ID |
| `run_id` | `VARCHAR(64)` | NOT NULL, INDEXED | Benchmark run identifier (e.g. `run-202611-v1`) |
| `incident_id` | `INTEGER` | FK `incidents.id` ON DELETE CASCADE | Held-out replay incident ID |
| `memory_on` | `BOOLEAN` | NOT NULL | Evaluation condition |
| `top1_correct` | `BOOLEAN` | NOT NULL | Did top-1 hypothesis match ground truth? |
| `top3_correct` | `BOOLEAN` | NOT NULL | Was ground truth in top-3 hypotheses? |
| `minutes_to_hypothesis` | `DOUBLE PRECISION` | NOT NULL | Simulated or real latency to hypothesis |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT NOW | Benchmark timestamp |

*Constraint:* `UNIQUE(run_id, incident_id, memory_on)`

---

## 3. Proposal for Postmortem Data (Action Item for Backend)

The prompt requests postmortem support without defining a table. We propose a dedicated table:

```sql
CREATE TABLE IF NOT EXISTS postmortems (
    id SERIAL PRIMARY KEY,
    incident_id INTEGER UNIQUE NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    timeline_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    preventative_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    published_at TIMESTAMPTZ,
    author_id INTEGER REFERENCES engineers(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

**Alternative:** Store postmortem notes directly in `incidents.root_cause`.  
*Recommendation:* Keep the modular `postmortems` table. It does not alter the 9 required tables and provides rich structured data for Frontend's Incident Console.

---

## 4. Query Contracts for Backend Endpoints

The table below outlines how Backend queries map to the database schema:

| Backend Endpoint | Query Pattern | Relevant Tables |
|---|---|---|
| `GET /services` | `SELECT * FROM services ORDER BY tier, name` | `services`, `engineers` |
| `GET /services/{id}/deploys` | `SELECT * FROM deploys WHERE service_id = :id ORDER BY deployed_at DESC LIMIT 10` | `deploys` |
| `GET /incidents` | `SELECT * FROM incidents ORDER BY opened_at DESC` | `incidents`, `alerts` |
| `GET /incidents/{code}` | `SELECT i.*, a.metric, a.value, a.payload FROM incidents i LEFT JOIN alerts a ON i.alert_id = a.id WHERE i.code = :code` | `incidents`, `alerts` |
| `GET /incidents/{code}/logs` | `SELECT * FROM log_lines WHERE incident_id = :inc_id ORDER BY ts ASC` | `log_lines` |
| `GET /incidents/{code}/fixes` | `SELECT * FROM fix_attempts WHERE incident_id = :inc_id ORDER BY at ASC` | `fix_attempts` |
| `POST /incidents/{code}/feedback`| `UPDATE agent_suggestions SET accepted = :accepted WHERE id = :id` | `agent_suggestions` |
| `POST /replay/results` | `INSERT INTO replay_results (...) VALUES (...)` | `replay_results` |
| `POST /demo/reset` | Calls `data.reset_database.reset_database()` | All tables |

---

## 5. Assumptions Requiring Backend & Team Sign-Off

1. **Primary Keys:** Using `INTEGER SERIAL` for high-throughput relational indexing and simple query debugging.
2. **Postmortems Table:** Proposing the `postmortems` table as an optional extension rather than forcing raw text into `incidents`.
3. **Dataset Partitioning:**
   - Historical Memory Bank (`kartly-sre`): Incidents `INC-0001` to `INC-0070`.
   - Held-Out Evaluation Replay: Incidents `INC-0071` to `INC-0110`.
   - **Zero leakage guarantee:** Replay incidents are excluded from Hindsight memory during initial seeding.
4. **Log Retention:** Raw operational logs are stored in PostgreSQL only. Under no circumstances are raw log lines forwarded to Hindsight.
