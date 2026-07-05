"""
Governance toggle for the ablation study.

Production is ALWAYS governed. Setting the environment variable
``AGENT_GOVERNANCE=off`` flips the agent into its ungoverned ablation:
no admissibility gate, no inference-state machine, per-cell (pseudoreplicating)
inference tools, and LLM-narrated replies (no deterministic renderer).

This exists purely to run a real end-to-end ungoverned baseline for the paper.
"""

from __future__ import annotations

import os


def governance_enabled() -> bool:
    """True unless AGENT_GOVERNANCE is explicitly set to 'off'/'0'/'false'."""
    val = os.getenv("AGENT_GOVERNANCE", "on").strip().lower()
    return val not in ("off", "0", "false", "no")
