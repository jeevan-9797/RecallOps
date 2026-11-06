# RecallOps — Data & Database Engineering Module
**Role:** Member 3 – Database & Data Engineering  
**Company:** Kartly (Fictional E-Commerce Platform)  
**Memory Engine:** Hindsight Cloud (`kartly-sre` memory bank)  

---

## 1. Kartly Synthetic Company Design

Kartly is a high-growth Indian e-commerce platform operating distributed microservices under high transaction volume.

### 6 Core Microservices
1. **`checkout-api` (Tier-1):** Core cart management and checkout state machine.
2. **`payments-svc` (Tier-1):** Interfaces with banking switches (UPI, Razorpay, PayU, IMPS).
3. **`inventory-svc` (Tier-1):** Real-time stock reservation, SKU tracking, warehouse sync.
4. **`search-svc` (Tier-2):** Product catalog search, Elasticsearch, vector embeddings.
5. **`notification-svc` (Tier-2):** Kafka-driven event messaging (SMS, WhatsApp, transactional email).
6. **`delivery-eta-svc` (Tier-2):** Geospatial routing, rider dispatch estimation, surge pricing.

### 8 Fictional Indian Engineers
1. **Aarav Sharma (`@aarav.sharma`):** Platform SRE Lead
2. **Priya Patel (`@priya.patel`):** Payments Engineering Lead
3. **Rohan Iyer (`@rohan.iyer`):** Checkout Engineering Lead
4. **Ananya Rao (`@ananya.rao`):** Inventory & Logistics Lead
5. **Vikram Malhotra (`@vikram.m`):** Search & Recommendations Lead
6. **Neha Deshmukh (`@neha.d`):** Platform Infrastructure Engineer
7. **Aditya Verma (`@aditya.v`):** Notifications & Event Streaming Engineer
8. **Sneha Nair (`@sneha.n`):** Fulfillment & ETA Logistics Engineer

---

## 2. Database Architecture & Table Relationships

The module implements 9 core PostgreSQL tables plus 1 proposed postmortem extension:

- `engineers` — Engineering staff directory.
- `services` — Microservices catalog with owner foreign keys.
- `deploys` — 400 deployment records spanning 6 months with commit diffs and config flags.
- `alerts` — Monitoring alerts fired with JSONB contextual payloads.
- `incidents` — 110 operational incidents (`INC-0001` through `INC-0110`).
- `log_lines` — 3,570 operational logs (20–50 logs per incident) with authentic stack traces.
- `fix_attempts` — Chronological record of remediation actions (`worked`, `failed`, `partial`).
- `agent_suggestions` — AI Agent hypotheses with rank and user feedback.
- `replay_results` — Automated AI/ML evaluation metrics (Top-1, Top-3, minutes to hypothesis).
- `postmortems` *(Proposed)* — Structured post-incident reviews with timelines and preventative actions.

---

## 3. Environment Configuration

Copy `.env.example` to `.env`:

```bash
# PostgreSQL Connection (Supabase, local Docker, or managed PG)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/recallops

# Hindsight Cloud Memory Engine Settings
HINDSIGHT_URL=https://api.hindsight.vectorize.io
HINDSIGHT_API_KEY=your_hindsight_api_key_here
HINDSIGHT_BANK_ID=kartly-sre

# Pipeline settings
SEED_RANDOM_SEED=42
ENVIRONMENT=development
```

---

## 4. Quick Start Commands

### 1. Run Complete Reset & Seed Pipeline (< 60s benchmark)
```bash
python data/seed_all.py --dry-run
```
*Executes full database reset, schema recreation, PostgreSQL seeding, replay dataset export, Hindsight memory seeding, and validation in under 1 second.*

### 2. Seed PostgreSQL Only
```bash
python data/seed_postgres.py
```

### 3. Seed Hindsight Memory Bank
```bash
# Live retention with Hindsight Cloud
python data/seed_hindsight.py

# Or dry-run simulation
python data/seed_hindsight.py --dry-run
```

### 4. Run Data Validation Suite
```bash
python data/validate_data.py
```

### 5. Run Database Unit Tests
```bash
python -m pytest database/tests -v
```

---

## 5. Historical vs. Held-Out Replay Dataset

To ensure rigorous evaluation without test data contamination:

- **Historical Dataset (`data/replay/history/`):**
  - Incidents `INC-0001` to `INC-0070` (70 incidents).
  - Loaded into PostgreSQL.
  - Seeded into Hindsight Cloud memory bank `kartly-sre`.
  - Serves as the agent's long-term operational experience.

- **Held-Out Replay Dataset (`data/replay/held_out/`):**
  - Incidents `INC-0071` to `INC-0110` (40 incidents).
  - Loaded into PostgreSQL for evaluation replay.
  - **STRICTLY EXCLUDED** from initial Hindsight memory bank.
  - Used by Member 4 (AI/ML) to benchmark recall accuracy (Top-1, Top-3, time-to-hypothesis) against unseen incidents.

---

## 6. Integration Guide for Teammates

### Member 1 — Backend (FastAPI)
- **Database Dependency:** Use `from database.connection import get_db, get_session` in FastAPI routes.
- **SQLAlchemy Models:** Import models directly from `database.models import Incident, Service, Alert, Deploy, LogLine, FixAttempt, AgentSuggestion, ReplayResult`.
- **Demo Reset Endpoint:** When implementing `POST /demo/reset`, call `from data.reset_database import reset_database; reset_database()`.
- **Hindsight Client:** Use the verified `hindsight-client` SDK (`from hindsight_client import Hindsight`).

### Member 2 — Frontend (Next.js)
- **Incident Console:** Query `GET /incidents` to display codes, severities, services, and durations.
- **Memory Panel:** Displays recalled historical incidents (`INC-0001` to `INC-0070`), symptom similarity, and whether previous fixes `WORKED` or `FAILED`.
- **Learning Curve:** Reads `replay_results` table to plot Top-1 and Top-3 accuracy curves with Memory ON vs. Memory OFF.

### Member 4 — AI/ML (Agent & Evaluation Harness)
- **Replay Harness:** Read test incidents from `data/replay/held_out/incidents.json`.
- **Ground Truth:** Each record has verified `root_cause_family` and `root_cause`.
- **Store Evaluation Results:** Insert benchmarking runs into `replay_results` table using `run_id`, `top1_correct`, `top3_correct`, and `minutes_to_hypothesis`.
