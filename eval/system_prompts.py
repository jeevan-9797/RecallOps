"""
RecallOps System Prompts & Agent Persona Definitions (Evaluation Harness)
Author: Member 4 (AI/ML & Model)
Phase: Phase 1: Foundations (H2–H8)

Re-exports production system prompts and provides evaluation baseline prompts
for measuring Hindsight learning-curve delta.
"""

import sys
from pathlib import Path

# Ensure root repository is in sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

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
