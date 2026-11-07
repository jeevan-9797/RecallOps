"""
RecallOps Prompts Package
Houses system prompts, engineer style adapters, and triage persona definitions.
"""
from backend.app.prompts.system_prompts import (
    BASELINE_NAIVE_SRE_PROMPT,
    PRODUCTION_RECALLOPS_SRE_PROMPT,
    SENIOR_SRE_SYSTEM_PROMPT,
    build_sre_system_prompt,
)

__all__ = [
    "SENIOR_SRE_SYSTEM_PROMPT",
    "PRODUCTION_RECALLOPS_SRE_PROMPT",
    "BASELINE_NAIVE_SRE_PROMPT",
    "build_sre_system_prompt",
]
