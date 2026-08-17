"""
Governance toggle for the ablation study.

Production is ALWAYS governed. The ungoverned ablation requires both
``AGENT_GOVERNANCE=off`` and ``AGENT_EVALUATION_CONTEXT=null_harness``:
no admissibility gate, no inference-state machine, raw LLM payloads, and
LLM-narrated replies (no deterministic renderer). Both arms retain identical
inferential methods, including donor-level pseudobulk DESeq2.

This exists purely to run a real end-to-end ungoverned baseline for the paper.
"""

from __future__ import annotations

import os


def governance_enabled() -> bool:
    """Return False only inside the explicitly identified null harness."""
    val = os.getenv("AGENT_GOVERNANCE", "on").strip().lower()
    requested_off = val in ("off", "0", "false", "no")
    evaluation_context = os.getenv("AGENT_EVALUATION_CONTEXT", "").strip().lower()
    return not (requested_off and evaluation_context == "null_harness")
