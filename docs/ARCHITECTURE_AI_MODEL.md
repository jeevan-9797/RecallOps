# RecallOps AI/ML & Model Architecture (Member 4)

**Owner:** Member 4 (AI/ML & Model)  
**Hackathon:** Hindsight AI Agents Hackathon  
**Phase:** Phase 0 (H0-H2 Kickoff) -> Phase 1 Foundation  

---

## 1. Role Scope & Ownership

Member 4 owns the cognitive brain, tool interfaces, memory logic, and evaluation framework for RecallOps:
1. **System Prompts & Tool Descriptions:** Authoring senior SRE prompts, calibrated confidence instructions, and tool calling definitions.
2. **Memory Retention & Recall Formatting:** Formatting data for ingestion and retrieval in Hindsight Cloud.
3. **Negative-Memory Logic:** Preventing recurring operational anti-patterns and repeating historical failed fixes.
4. **Replay Evaluation Harness & Learning-Curve Verification:** Designing deterministic replay benchmarks measuring agent performance improvement over time.

---

## 2. Directory Structure

```
RecallOps/
├── .env.example                         # Environment config template
├── docs/
│   ├── ARCHITECTURE_AI_MODEL.md         # This architecture document
│   ├── TOOL_CONTRACTS.md                # Tool specifications & response schemas
│   └── HINDSIGHT_MEMORY_SPEC.md         # Hindsight retention & negative-memory logic
├── backend/
│   └── app/
│       ├── __init__.py
│       └── schemas/
│           ├── __init__.py
│           └── agent_tools.py           # Pydantic v2 tool & response definitions
└── eval/
    ├── __init__.py
    ├── schemas.py                       # Re-export & CLI schema introspection
    ├── system_prompts.py                # Senior SRE & Replay system prompts
    ├── hand_off_contract.json           # OpenAI/Groq compatible tools array export
    ├── contract_metadata.json           # Full schema bundle & contract metadata
    ├── generate_contracts.py            # Automated contract generator script
    ├── test_schemas.py                  # Pytest suite for Pydantic v2 schemas
    └── test_groq_tools.py               # Groq function-calling smoke test script
```

---

## 3. Phase 0 Deliverables Summary

| Deliverable | File Location | Status | Description |
|---|---|---|---|
| **1. Directories** | `/eval`, `/docs`, `/backend/app/schemas` | Complete | Directory structure set up with proper python packaging |
| **2. Pydantic Schemas** | `backend/app/schemas/agent_tools.py`, `eval/schemas.py` | Complete | 6 Function calling tool models + `AgentTriageResponse` |
| **3. Groq Smoke Test** | `eval/test_groq_tools.py` | Complete | Standalone test script testing `openai/gpt-oss-120b` & `qwen/qwen3-32b` with toy `enable_antigravity` tool |
| **4. Hand-off Contract**| `eval/hand_off_contract.json` | Complete | Clean, pre-compiled JSON tools array for Member 1 (Backend) |

---

## 4. Target Model Evaluation Strategy

### Selected Models on Groq:
1. **`openai/gpt-oss-120b` (Primary Reasoning Engine):** High-parameter reasoning model for deep causal inference, multi-hop log correlation, and synthesis.
2. **`qwen/qwen3-32b` (Fast Triage & Function Calling):** Low-latency 32B model optimized for rapid tool calling, classification, and initial triage screening.

### Function Calling Validation:
`eval/test_groq_tools.py` validates that:
- SRE system prompts induce tool selection when alerts arrive.
- The model calls `enable_antigravity`.
- Arguments match expected types (`service_name: str`, `power_level: int`).

---

## 5. Phase 1 Roadmap (H2-H8)

1. **Replay Benchmark Dataset (`/eval/benchmarks/`):**
   - Curate 10 synthetic incidents with gold-standard root causes and verified failed fixes.
2. **Automated Replay Runner (`/eval/replay_harness.py`):**
   - Replay each incident in naive mode (no memory) vs. RecallOps mode (with Hindsight Cloud memory).
3. **Learning-Curve Verification:**
   - Measure Diagnostic Accuracy, MTTR Reduction, and 0% Negative-Memory repetition.
