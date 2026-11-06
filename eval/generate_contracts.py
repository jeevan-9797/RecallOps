"""
Contract Generator Script
Exports OpenAI/Groq compatible tool definitions and AgentTriageResponse schemas
to /eval/hand_off_contract.json for Member 1 (Backend).
"""

import json
import sys
from pathlib import Path

# Ensure root repository directory is in sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.schemas.agent_tools import (
    get_openai_tool_definitions,
    get_agent_response_schema,
)

def export_hand_off_contracts(output_path: Path | None = None) -> Path:
    """Exports the 6 function tools to JSON array for backend import."""
    if output_path is None:
        output_path = Path(__file__).resolve().parent / "hand_off_contract.json"

    tools = get_openai_tool_definitions()

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(tools, f, indent=2)

    print(f"[SUCCESS] Exported {len(tools)} tool definitions to {output_path}")

    # Also export companion metadata / full contract for convenience
    meta_path = output_path.parent / "contract_metadata.json"
    bundle = {
        "_meta": {
            "version": "1.0.0",
            "phase": "Phase 0 Kickoff / Foundation",
            "owner": "Member 4 (AI/ML & Model)",
            "description": "Hand-off contract for Backend (Member 1) to import into FastAPI agent loop.",
        },
        "tools": tools,
        "agent_response_schema": get_agent_response_schema(),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)

    print(f"[SUCCESS] Exported contract metadata & response schema to {meta_path}")
    return output_path


if __name__ == "__main__":
    export_hand_off_contracts()
