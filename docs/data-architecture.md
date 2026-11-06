# RecallOps — Data Architecture & Operational Pipeline
**Author:** Member 3 (Database & Data Engineering)  
**Target Roles:** Entire RecallOps Team  
**Version:** 1.0.0  

---

## 1. System Overview

RecallOps pairs an operational relational database (PostgreSQL) with a long-term semantic memory engine (Hindsight Cloud) to provide SRE agents with contextual recall of recurring failure patterns.

```mermaid
graph TD
    subgraph PostgreSQL Relational Store
        ENG[engineers] -->|owns| SVC[services]
        ENG -->|authors| DEP[deploys]
        SVC -->|triggers| ALR[alerts]
        SVC -->|has| DEP
        ALR -->|originates| INC[incidents]
        INC -->|contains| LOG[log_lines]
        INC -->|tracks| FIX[fix_attempts]
        INC -->|evaluates| SUG[agent_suggestions]
        INC -->|benchmarks| REP[replay_results]
        INC -.->|optional| PM[postmortems]
    end

    subgraph Data Pipeline & Replay Partition
        GEN[Dataset Generator seed=42] -->|110 Incidents| SPLIT{Dataset Splitter}
        SPLIT -->|INC-0001 to INC-0070| HIST[Historical Dataset]
        SPLIT -->|INC-0071 to INC-0110| HELD[Held-Out Replay Dataset]
        HIST -->|Bulk Insert| PostgreSQL
        HELD -->|Bulk Insert| PostgreSQL
        HIST -->|Format & Retain| HINDSIGHT[(Hindsight Cloud Bank 'kartly-sre')]
        HELD -.->|STRICT EXCLUSION: No Leaks| HINDSIGHT
    end
```

---

## 2. Entity-Relationship Model

```mermaid
erDiagram
    engineers ||--o{ services : "owns"
    engineers ||--o{ deploys : "authors"
    engineers ||--o{ fix_attempts : "executes"
    services ||--o{ deploys : "tracks"
    services ||--o{ alerts : "emits"
    alerts ||--o{ incidents : "triggers"
    incidents ||--o{ log_lines : "records"
    incidents ||--o{ fix_attempts : "chronicles"
    incidents ||--o{ agent_suggestions : "receives"
    incidents ||--o{ replay_results : "benchmarks"
    incidents ||--o| postmortems : "generates"

    engineers {
        int id PK
        varchar name
        varchar team
        varchar slack_handle UK
    }

    services {
        int id PK
        varchar name UK
        varchar team
        int owner_id FK
        varchar tier
    }

    deploys {
        int id PK
        int service_id FK
        int author_id FK
        timestamptz deployed_at
        text summary
        boolean config_change
        text diff_note
    }

    alerts {
        int id PK
        int service_id FK
        varchar metric
        float threshold
        float value
        timestamptz fired_at
        jsonb payload
    }

    incidents {
        int id PK
        varchar code UK
        int alert_id FK
        varchar severity
        varchar status
        timestamptz opened_at
        timestamptz resolved_at
        text root_cause
        varchar root_cause_family
        int duration_min
    }

    log_lines {
        int id PK
        int incident_id FK
        timestamptz ts
        varchar level
        varchar source
        text message
    }

    fix_attempts {
        int id PK
        int incident_id FK
        text action
        varchar outcome
        int by_engineer FK
        timestamptz at
    }

    agent_suggestions {
        int id PK
        int incident_id FK
        text hypothesis
        int rank
        boolean memory_on
        boolean accepted
    }

    replay_results {
        int id PK
        varchar run_id
        int incident_id FK
        boolean memory_on
        boolean top1_correct
        boolean top3_correct
        float minutes_to_hypothesis
    }
```

---

## 3. Recurring Root-Cause Families

The synthetic dataset implements 8 recurring failure patterns grounded in real-world distributed systems:

| Family Key | Description | Primary Services | Metric Signature | Authentic Log Sources | Typical Failed Fix | Ground-Truth Worked Fix |
|---|---|---|---|---|---|---|
| `db_pool` | Connection pool exhaustion | `checkout-api`, `inventory-svc`, `payments-svc` | `db_connection_pool_active_ratio > 0.90` | `HikariCP`, `PostgreSQL` | Restart application pods | Increase pool size to 65 & fix connection leak |
| `redis_eviction`| Eviction storm under flash sale | `inventory-svc`, `search-svc`, `checkout-api` | `redis_memory_usage_ratio > 0.85` | `RedisServer`, `CacheManager` | Flush Redis cache | Upgrade to r6g.2xlarge (32GB) & switch to MessagePack |
| `tls_expiry` | Expired ingress or mTLS cert | `payments-svc`, `checkout-api`, `delivery-eta-svc`| `cert_expiry_seconds < 86400` | `NginxIngress`, `CertManager` | Disable HTTP/2 | Re-issue cert via cert-manager & reload Envoy |
| `payment_timeout`| Payment gateway latency & drops | `payments-svc`, `checkout-api` | `payment_gateway_failure_rate > 0.05` | `PyRazorpay`, `PaymentEngine` | Increase HTTP timeout to 60s | Route traffic to fallback gateway (PayU/HDFC) |
| `feature_flag` | Malformed config / unhandled None | `checkout-api`, `search-svc`, `inventory-svc` | `http_5xx_error_rate > 0.02` | `UnleashSDK`, `CheckoutController`| Restart deployment | Toggle flag OFF in Unleash console |
| `disk_full` | Logrotate failure / disk 100% | `search-svc`, `notification-svc`, `delivery-eta-svc`| `disk_partition_used_ratio > 0.85` | `SystemdJournal`, `Logrotate` | Restart application | Fix logrotate cron, purge debug logs, resize EBS |
| `n_plus_one` | Lazy loading query regression | `search-svc`, `checkout-api`, `inventory-svc` | `database_cpu_utilization > 0.80` | `SQLAlchemyLogger`, `PostgreSQL`| Horizontally scale pods | Rewrite query with eager loading (`joinedload`) |
| `kafka_lag` | Consumer lag / rebalance storm | `notification-svc`, `delivery-eta-svc` | `kafka_consumer_group_lag > 10000` | `KafkaConsumer`, `KafkaBroker` | Kill/restart consumer pods | Increase `max.poll.interval.ms` & scale pods |

---

## 4. Hindsight Memory Retention Protocol

### Template Architecture
Memories retained in Hindsight Cloud follow a standardized, token-efficient structure:

```text
[INC-0001]
[checkout-api]
[family: db_pool]

Symptom:
Alert fired for db_connection_pool_active_ratio (value: 0.985, threshold: 0.90).

Deployment:
Deployment 'perf(db): tune pool size' was pushed (config_change=True).

Failed fix:
Restarted service deployment pods (connections exhausted again within 2 minutes)

Outcome:
FAILED.

Root cause:
HikariCP connection pool exhausted due to unclosed database connections during peak traffic surge.

Successful fix:
Increased RDS Postgres max_connections to 400 and tuned HikariCP maximumPoolSize to 65

Outcome:
WORKED.

Resolution time:
35 minutes.
```

### Context Tags
Each memory unit in Hindsight is indexed with:
- `INC-xxxx` (Incident Code)
- Service name (e.g. `checkout-api`)
- `family:<family_key>` (Root-cause classification)
- `severity:<P1..P4>` (Criticality)
- `historical_incident` (Partition flag)

---

## 5. Evaluation Separation & Held-Out Partition

To maintain strict scientific validity:
- **Historical Partition (INC-0001 to INC-0070):** 70 incidents loaded into PostgreSQL AND retained into Hindsight bank `kartly-sre`.
- **Held-Out Replay Partition (INC-0071 to INC-0110):** 40 incidents loaded into PostgreSQL for replay evaluation, but **strictly excluded from Hindsight memory**.
- **Agent Evaluation Loop:** During replay, Member 4's AI/ML harness queries Hindsight for memories matching the symptom of incident `INC-xxxx`. Because the incident itself was never seen by Hindsight, the agent must recall analogous historical incidents (from INC-0001 to INC-0070) that share the root-cause family and recommend the successful fix while warning against the failed fix.
