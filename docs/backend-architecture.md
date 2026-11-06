# RecallOps Backend Architecture Specification

**Role:** Senior Backend Architect  
**Version:** 1.1.0 (Phase 1 Foundation)  

---

## 1. System Topology & Layers

RecallOps is built as an event-driven, dual-memory incident response backend:

```
[ Monitoring / PagerDuty / Webhook ]
                |
                v  POST /api/alerts
+-------------------------------------------------------------------------+
|                           FastAPI Gateway                               |
|   - CORS Middleware (Next.js localhost:3000)                            |
|   - Global Exception Handling (RFC 7807 JSON)                           |
|   - OpenAPI Contract Registry (/docs)                                   |
+-------------------------------------------------------------------------+
                |
                +---> POST /api/incidents/{id}/triage (SSE Stream)
                |
                v
+-------------------------------------------------------------------------+
|                  Groq ReAct SRE Agent Loop                              |
|   - System Prompts: Senior SRE (Production) vs Naive (Baseline)         |
|   - Primary Model: openai/gpt-oss-120b                                  |
|   - Fallback Model: qwen/qwen3-32b                                      |
|   - Turn Budget: 6 maximum iterations                                   |
|   - Tool Dispatcher: parameter validation via Pydantic v2 schemas       |
+-------------------+---------------------------------+-------------------+
                    |                                 |
                    v                                 v
+-------------------------------------+   +-------------------------------+
|      Operational Truth (Facts)      |   |   Cognitive Memory (Experience|
|          PostgreSQL 16              |   |        Hindsight Cloud        |
|-------------------------------------|   |-------------------------------|
| - services                          |   | - retain() postmortems        |
| - engineers                         |   | - retain() negative fixes     |
| - deploys (get_recent_deploys)      |   | - recall() episodic matches   |
| - alerts                            |   | - recall() failed fix blocks  |
| - incidents                         |   | - reflect() learned patterns  |
| - log_lines (get_logs)              |   |                               |
| - fix_attempts                      |   | Bank: kartly-sre              |
| - agent_suggestions                 |   +-------------------------------+
| - replay_results                    |                   |
+-------------------------------------+                   v
                    |                      +------------------------------+
                    v                      |      Multi-Agent Virtual     |
+-------------------------------------+    |         Incident Room        |
|       SQLAlchemy 2.0 Repository     |    |       Band Room Adapter      |
|     (AsyncSession + asyncpg)        |    +------------------------------+
+-------------------------------------+
```

---

## 2. ReAct Agent Loop & Failover Sequence
1. **System Prompt Injection:** Injects `PRODUCTION_RECALLOPS_SRE_PROMPT` containing negative-memory guardrails.
2. **Tool Execution:** Tool calls (`recall_similar_incidents`, `recall_failed_fixes`, `get_recent_deploys`, `get_logs`, `get_service_owner`, `post_to_band_room`) are executed asynchronously through `AgentToolDispatcher`.
3. **Model Failover:** On HTTP 429, 500, or connection timeout with `openai/gpt-oss-120b`, the agent seamlessly re-issues the completion to `qwen/qwen3-32b`.
4. **Output Parsing:** Concludes with typed `AgentTriageResponse` JSON validated by Pydantic.

---

## 3. Database Layer & Repository Pattern
* **Engine:** `SQLAlchemy 2.0` with `asyncpg` async driver.
* **Separation of Concerns:** `DatabaseRepositoryInterface` abstracts domain queries from SQL mechanics.
* **Tables:** Conforms to the Database Lead's 9-table schema (`services`, `engineers`, `deploys`, `alerts`, `incidents`, `log_lines`, `fix_attempts`, `agent_suggestions`, `replay_results`).
