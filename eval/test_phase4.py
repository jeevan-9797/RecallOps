"""
Unit Tests for Phase 4: Polish + Freeze (Code Freeze & Verification)
Author: Member 4 (AI/ML & Model)
Phase: Phase 4: Polish + Freeze (H22–H28)
"""

from pathlib import Path
import pytest

from eval.verify_reproducibility import run_reproducibility_check
from backend.app.prompts.system_prompts import (
    SENIOR_SRE_SYSTEM_PROMPT,
    build_sre_system_prompt,
)


# ==============================================================================
# 1. DOCUMENTATION INTEGRITY & COVERAGE
# ==============================================================================

def test_memory_design_doc_exists_and_covers_requirements():
    repo_root = Path(__file__).resolve().parent.parent
    design_doc = repo_root / "docs" / "memory-design.md"
    assert design_doc.exists(), "docs/memory-design.md must exist for judging review"

    content = design_doc.read_text(encoding="utf-8")

    # Verify key architectural topics
    assert "Executive Summary" in content or "Core Differentiator" in content
    assert "kartly-sre" in content
    assert "engineer-{engineer_id}" in content or "engineer-priya" in content
    assert "Tripartite" in content
    assert "Negative Memory" in content or "failed fixes" in content
    assert "Learning Curve" in content
    assert "40 held-out" in content or "Incidents 71" in content
    assert "Top-1 Root Cause Accuracy" in content
    assert "MTTR" in content

    # Verify absence of placeholders
    assert "TODO:" not in content
    assert "TODO " not in content
    assert "FIXME" not in content
    assert "TBD" not in content


# ==============================================================================
# 2. PROMPT FREEZE & COMPLETENESS
# ==============================================================================

def test_system_prompts_frozen_and_clean():
    repo_root = Path(__file__).resolve().parent.parent
    prompt_file = repo_root / "backend" / "app" / "prompts" / "system_prompts.py"
    assert prompt_file.exists()

    content = prompt_file.read_text(encoding="utf-8")

    # Ensure no unresolved TODOs
    assert "TODO" not in content
    assert "FIXME" not in content

    # Ensure mandatory SRE prompt guardrails
    assert "[INC-1987]" in SENIOR_SRE_SYSTEM_PROMPT
    assert "No historical memory match found." in SENIOR_SRE_SYSTEM_PROMPT
    assert "failed_fixes_warning" in SENIOR_SRE_SYSTEM_PROMPT
    assert "priya" in SENIOR_SRE_SYSTEM_PROMPT.lower()
    assert "rahul" in SENIOR_SRE_SYSTEM_PROMPT.lower()
    assert "confidence" in SENIOR_SRE_SYSTEM_PROMPT.lower()
    assert "AgentTriageResponse" in SENIOR_SRE_SYSTEM_PROMPT

    # Test dynamic prompt builder functionality
    dynamic_prompt = build_sre_system_prompt(
        engineer_id="priya",
        engineer_preference="Runnable kubectl commands only",
        recalled_incident_memories="[INC-1987] DB pool exhausted",
        recalled_failed_fixes="[INC-1987] Do NOT restart db",
    )
    assert "priya" in dynamic_prompt
    assert "[INC-1987] DB pool exhausted" in dynamic_prompt
    assert "Do NOT restart db" in dynamic_prompt


# ==============================================================================
# 3. REPRODUCIBILITY & STABILITY VERIFICATION
# ==============================================================================

def test_evaluation_reproducibility_passes():
    """Executes the dual-pass reproducibility verification harness."""
    success = run_reproducibility_check(verbose=False)
    assert success is True, "Reproducibility check failed: evaluation metrics must be 100% deterministic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
