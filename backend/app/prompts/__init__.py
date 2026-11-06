"""
RecallOps Prompts Package
Houses system prompts, engineer style adapters, and triage persona definitions.
"""
from backend.app.prompts.system_prompts import (
    SENIOR_SRE_SYSTEM_PROMPT,
    build_sre_system_prompt,
)

__all__ = [
    "SENIOR_SRE_SYSTEM_PROMPT",
    "build_sre_system_prompt",
]
