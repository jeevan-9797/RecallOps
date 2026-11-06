# RecallOps Backend 🚀

> **FastAPI Backend & Cognitive Dual-Memory Orchestrator for RecallOps**  
> *Hindsight AI Agents Hackathon*

---

## 🛠️ Stack & Technologies
* **Framework:** FastAPI with Uvicorn
* **Python Runtime:** Python 3.11
* **Memory Engine:** Hindsight Cloud (`hindsight-client` v1.2.0, default bank: `kartly-sre`)
* **LLM Orchestration:** Groq Cloud (`openai/gpt-oss-120b` primary, `qwen/qwen3-32b` fallback)
* **Operational Database:** PostgreSQL 16 (Local Docker via `docker-compose.yml` / Hosted Supabase)
* **Streaming Protocol:** Server-Sent Events (SSE) via `sse-starlette`
* **Multi-Agent Comms:** Band Room Adapter (`BandAdapterInterface` + `MockBandAdapter`)

---

## 🚀 Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Set your GROQ_API_KEY and HINDSIGHT_API_KEY in .env
```

### 3. Start Local PostgreSQL (Docker)
```bash
docker compose up -d
```

### 4. Run the FastAPI Development Server
```bash
uvicorn backend.app.main:app --reload --port 8000
```
* **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Health Check:** [http://localhost:8000/health](http://localhost:8000/health)

### 5. Run Test Suite
```bash
pytest -v
```

---

## 📦 Architecture Highlights
1. **Rule of Separation:**
   * PostgreSQL stores system facts (services, deploys, alerts, incidents, logs, fix attempts).
   * Hindsight Cloud stores experiential cognitive memory (episodic incident resolutions, failed fixes negative memory, learned patterns via `reflect()`).
2. **Deterministic Model Failover:**
   * The agent loop targets `openai/gpt-oss-120b` for deep causal SRE reasoning.
   * If Groq rate limits (429) or timeouts occur, it automatically falls back to `qwen/qwen3-32b`.
3. **Provable Memory Ablation:**
   * Calling `/api/incidents/{id}/triage?memory=off` runs the naive baseline agent without Hindsight augmentation, enabling live comparative demonstrations.
