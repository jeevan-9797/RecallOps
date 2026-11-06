"""
RecallOps Evaluation & Tool Schemas
Author: Member 4 (AI/ML & Model)
Phase: Phase 0 Kickoff

Shared interface providing:
- Pydantic models for the 6 incident triage tools
- Structured AgentTriageResponse output contract
- OpenAI/Groq function calling specifications
"""

import sys
from pathlib import Path

# Ensure root repository directory is in sys.path for direct script execution
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.schemas.agent_tools import (
    RecallSimilarIncidentsInput,
    RecallFailedFixesInput,
    GetRecentDeploysInput,
    GetLogsInput,
    GetServiceOwnerInput,
    PostToBandRoomInput,
    AgentTriageResponse,
    build_tool_definition,
    get_openai_tool_definitions,
    get_agent_response_schema,
    TOOL_DEFINITIONS,
)

__all__ = [
    "RecallSimilarIncidentsInput",
    "RecallFailedFixesInput",
    "GetRecentDeploysInput",
    "GetLogsInput",
    "GetServiceOwnerInput",
    "PostToBandRoomInput",
    "AgentTriageResponse",
    "build_tool_definition",
    "get_openai_tool_definitions",
    "get_agent_response_schema",
    "TOOL_DEFINITIONS",
]

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("RecallOps Pydantic v2 Schemas & Tool Definitions")
    print("=" * 60)
    tools = get_openai_tool_definitions()
    print(f"\n[+] Defined {len(tools)} Function Calling Tools:")
    for idx, t in enumerate(tools, 1):
        func = t["function"]
        props = list(func["parameters"]["properties"].keys())
        req = func["parameters"]["required"]
        print(f"  {idx}. {func['name']} (params: {props}, required: {req})")

    print("\n[+] AgentTriageResponse JSON Schema:")
    print(json.dumps(get_agent_response_schema(), indent=2))
