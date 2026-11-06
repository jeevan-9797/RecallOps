# RecallOps: Backend Execution Plan & Architecture Blueprint

**Project:** RecallOps — Autonomous SRE Incident Response Agent  
**Event:** Hindsight AI Agents Hackathon  
**Role:** Backend Lead & Senior Backend Architect  
**Active Branch:** `backend` (Base: `origin/main` / `origin/aiml`)  
**Target Stack:** Python 3.11, FastAPI, Groq LLM (`openai/gpt-oss-120b` primary, `qwen/qwen3-32b` fallback), Hindsight Cloud (`kartly-sre`), PostgreSQL (Local Docker / Hosted Supabase), SSE Streaming, Band Multi-Agent  
**Plan Version:** 1.1.0 (Phase 0 Implemented & Verified)  
**Execution Window:** P0 Kickoff (H0) through P5 Ship (H36)  

---

## 1. Approved Decisions & Architectural Guardrails

### 1.1 Approved Decisions Log
1. **Git Strategy:**
   * Dedicated `backend` branch created from remote baseline (`origin/main`), which contains the exact same 17 AI/ML schema and contract files as `origin/aiml`.
   * Preserved all existing AI/ML contracts without modification.
   * `aiml` and `main` branches are protected and never modified directly or force-pushed.
2. **Database Architecture:**
   * **Target Database:** PostgreSQL is the only production database.
   * **Development:** Local Docker PostgreSQL container for local development.
   * **Staging/Production:** Hosted Supabase PostgreSQL for cloud deployment.
   * In-memory mocks are strictly confined to Phase 0 prototyping and automated unit tests. SQLite is explicitly excluded from production.
3. **Band Multi-Agent Communication:**
   * Built an abstract adapter interface (`BandAdapterInterface`) and local development mock adapter (`MockBandAdapter`).
   * No synthetic or imaginary endpoints/credentials introduced. Live integration is deferred until the Research Lead confirms official Band SDK/API specifications.
4. **Hindsight Cloud Configuration:**
   * Configurable bank ID with approved default: `kartly-sre`.
   * Installed SDK: `hindsight-client` v1.2.0. Verified both synchronous and asynchronous client methods (`retain`/`aretain`, `recall`/`arecall`, `reflect`/`areflect`).
5. **AI/ML Contracts (Zero-Duplication):**
   * Reused all pre-existing Phase 0 contracts authored by Member 4:
     - `backend/app/schemas/agent_tools.py`
     - `eval/hand_off_contract.json`
     - `eval/system_prompts.py`
     - `eval/test_schemas.py`
     - `eval/test_groq_tools.py`
     - `docs/ARCHITECTURE_AI_MODEL.md`
     - `docs/HINDSIGHT_MEMORY_SPEC.md`
     - `docs/TOOL_CONTRACTS.md`

### 1.2 The Rule of Separation (Judges Criterion)
* **PostgreSQL / Supabase** stores **Facts about the system**: services, deployment history, runtime telemetry logs, incident state, and engineer feedback records.
* **Hindsight Cloud** stores **Experience**: episodic memory of what happened, attempted remediations, what worked, what failed (negative memory), and cross-incident learned observations (`reflect`).
* **Strict Invariant:** Never duplicate experience into PostgreSQL, and never store raw system operational state into Hindsight.

---

## 2. Repository Structure & Audit

### 2.1 Existing Files Reused vs. New Files Created

```
RecallOps/ (Branch: backend)
│
├── .env.example                         [UPDATED] Added HINDSIGHT_BANK_ID=kartly-sre, DATABASE_URL, etc.
├── .gitignore                           [UPDATED] Added *.log ignore rule
├── README.md                            [REUSED] Team quickstart and deliverables
├── requirements.txt                     [NEW] Master pinned dependencies (FastAPI, Groq, Hindsight, Supabase)
├── BACKEND_EXECUTION_PLAN.md            [UPDATED] This architectural execution document
│
├── docs/                                [REUSED AI/ML Specifications]
│   ├── ARCHITECTURE_AI_MODEL.md         (Existing Member 4 architecture specification)
│   ├── HINDSIGHT_MEMORY_SPEC.md         (Existing Member 4 dual-memory & negative-memory spec)
│   └── TOOL_CONTRACTS.md                (Existing Member 4 tool contracts)
│
├── backend/
│   └── app/
│       ├── __init__.py                  (Existing package marker)
│       ├── main.py                      [NEW] FastAPI application entrypoint with CORS & middleware
│       ├── config.py                    [NEW] Centralized pydantic-settings environment validation
│       │
│       ├── api/                         [NEW API Route Controllers]
│       │   ├── __init__.py
│       │   ├── router.py                [NEW] Master API router grouping /api routes
│       │   ├── health.py                [NEW] GET /health factual readiness probe
│       │   ├── alerts.py                [NEW] POST /api/alerts (creates incident)
│       │   ├── incidents.py             [NEW] POST /triage (SSE), POST /feedback, POST /resolve, GET /memories
│       │   ├── observations.py          [NEW] GET /api/observations (Hindsight reflect)
│       │   ├── metrics.py               [NEW] GET /api/metrics/learning-curve (eval replay)
│       │   └── demo.py                  [NEW] POST /api/demo/reset (1-click wipe & reseed)
│       │
│       ├── core/                        [NEW Core System Infrastructure]
│       │   ├── __init__.py
│       │   ├── sse.py                   [NEW] SSE event generator & protocol formatter
│       │   └── exceptions.py            [NEW] Centralized domain exceptions & HTTP handlers
│       │
│       ├── schemas/                     [Data Contracts]
│       │   ├── __init__.py              (Existing)
│       │   ├── agent_tools.py           [REUSED] 6 function tools + AgentTriageResponse
│       │   └── api_models.py            [NEW] Pydantic v2 schemas for all 9 REST/SSE endpoints
│       │
│       └── services/                    [Business Logic & Adapters]
│           ├── __init__.py
│           └── band_adapter.py          [NEW] BandAdapterInterface + MockBandAdapter
│
├── eval/                                [REUSED Member 4 AI/ML Test Harness]
│   ├── __init__.py
│   ├── contract_metadata.json
│   ├── generate_contracts.py
│   ├── hand_off_contract.json
│   ├── schemas.py
│   ├── system_prompts.py
│   ├── test_groq_tools.py               (Smoke test passes in --mock mode)
│   └── test_schemas.py                  (11 unit tests passing)
│
└── tests/                               [NEW Backend Unit & Integration Tests]
    ├── __init__.py
    └── test_api_p0.py                   [NEW] 15 comprehensive tests covering all 9 routes (26/26 tests pass)
```

---

## 3. Implemented API Contracts (Phase 0 Foundation)

All 9 endpoints are fully implemented and verified via automated test suites:

| Method | Endpoint | Status | Description |
|---|---|---|---|
| `GET` | `/health` | **Live** | Factual readiness report for Groq, Hindsight, and PostgreSQL |
| `POST` | `/api/alerts` | **Live** | Ingest alert, create tracked incident ID (`INC-2046`), returns 201 |
| `POST` | `/api/incidents/{id}/triage` | **Live** | SSE stream (`thought`, `tool_call`, `recalled_memory`, `warning`, `suggestion`, `done`) |
| `POST` | `/api/incidents/{id}/feedback` | **Live** | Ingest engineer feedback; sets `negative_memory_retained=True` if failed |
| `POST` | `/api/incidents/{id}/resolve` | **Live** | Ingest postmortem; sets `episodic_memory_retained=True` |
| `GET` | `/api/incidents/{id}/memories` | **Live** | Feed for UI Memory Panel showing cited positive and negative memories |
| `GET` | `/api/observations` | **Live** | Surfaces learned patterns synthesized via Hindsight `reflect()` |
| `GET` | `/api/metrics/learning-curve`| **Live** | 40-incident benchmark stats comparing memory OFF vs ON |
| `POST` | `/api/demo/reset` | **Live** | 1-click state reset for demo runs (reseeds 8 services, 45 deploys, 32 memories) |

---

## 4. Test Verification Results

* **Schema Tests (`eval/test_schemas.py`):** 11/11 tests pass.
* **API Integration Tests (`tests/test_api_p0.py`):** 15/15 tests pass.
* **Total Automated Tests:** 26/26 passing in 1.73 seconds.
* **Groq Function Calling Smoke Test (`eval/test_groq_tools.py --mock`):** 2/2 models (`openai/gpt-oss-120b`, `qwen/qwen3-32b`) verified passing.

---

## 5. Dependencies and Blockers Log

| Area | Current Status | Handoff Owner | Blocker Severity |
|---|---|---|---|
| **Frontend Shell** | Unblocked. Can connect to `http://localhost:8000/docs` and test all 9 routes immediately against mock SSE streams. | Member 2 (Frontend) | **NONE (UNBLOCKED)** |
| **PostgreSQL Schema** | Docker connection configured in `.env.example`. Awaiting Member 3's DDL migration scripts and synthetic incident seed dataset. | Member 3 (Database) | **LOW** (In-memory mock active) |
| **Groq Live API Key** | `groq` SDK v1.7.0 installed. Smoke test validated offline. Live calls require injecting `GROQ_API_KEY` into `.env`. | Member 4 / Team | **LOW** (Mock mode functional) |
| **Hindsight Live API Key**| `hindsight-client` v1.2.0 installed. Default bank `kartly-sre`. Live retain/recall requires injecting `HINDSIGHT_API_KEY`. | Member 4 / Team | **LOW** (Mock mode functional) |
| **Band Multi-Agent** | Abstract adapter interface implemented with `MockBandAdapter`. Waiting for Research Lead's live specification. | Member 5 (Research) | **LOW** (Decoupled by adapter) |
