# RecallOps 🚨🧠

> **Autonomous SRE Agent powered by Hindsight Cloud Episodic & Negative Memory**  
> *Hindsight AI Agents Hackathon*

---

## 🚀 Quickstart for Team Members

### 1. Environment Setup
```bash
# Clone and enter repo
cd RecallOps

# Install dependencies
pip install groq python-dotenv pydantic pytest

# Configure environment variables
cp .env.example .env
# Edit .env and paste your GROQ_API_KEY
```

### 2. Verify Pydantic Schemas & Contracts (Pytest)
```bash
python -m pytest eval/test_schemas.py -v
```

### 3. Run Groq Tool-Calling Smoke Test
```bash
# Run with mock pipeline (no API key needed)
python eval/test_groq_tools.py --mock

# Run live against Groq endpoint (requires GROQ_API_KEY in .env)
python eval/test_groq_tools.py
```

### 4. Re-generate Hand-off Contract for Backend
```bash
python eval/generate_contracts.py
```

---

## 📦 Deliverables & Repository Structure

* **`eval/hand_off_contract.json`**: Pre-compiled OpenAI/Groq function calling tools array ready for Member 1 (Backend) to plug into `tools=`.
* **`backend/app/schemas/agent_tools.py`**: Pydantic v2 schemas for all 6 incident tools and the structured `AgentTriageResponse` contract.
* **`eval/test_groq_tools.py`**: Smoke test verifying tool-calling on `openai/gpt-oss-120b` and `qwen/qwen3-32b`.
* **`docs/`**:
  * [`ARCHITECTURE_AI_MODEL.md`](docs/ARCHITECTURE_AI_MODEL.md): Member 4 architecture, model strategy, and Phase 1 roadmap.
  * [`TOOL_CONTRACTS.md`](docs/TOOL_CONTRACTS.md): Detailed specifications for all 6 tools and output response schema.
  * [`HINDSIGHT_MEMORY_SPEC.md`](docs/HINDSIGHT_MEMORY_SPEC.md): Hindsight Cloud memory retention, episodic retrieval, and negative-memory guardrails.
