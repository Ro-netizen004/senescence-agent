"""
Clinical-style inference state machine (A–E).

System assigns state from tool facts; renderer decides all user-facing wording.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

ALPHA = 0.05
RECOMMENDED_SAMPLES_PER_GROUP = 3
MIN_CELLS_PER_GROUP_INFERENCE = 20
MIN_PSEUDOBULK_SAMPLES_PER_AGE = 2


class InferenceState(str, Enum):
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"  # A
    LOW_POWER = "LOW_POWER"  # B
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"  # C
    SIGNIFICANT_INFERENTIAL = "SIGNIFICANT_INFERENTIAL"  # D
    BLOCKED = "BLOCKED"  # E


class InterpretationLevel(str, Enum):
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    INFERENTIAL = "INFERENTIAL"
    BLOCKED = "BLOCKED"


# Per-state contracts: renderer enforces these; LLM must not override.
STATE_CONTRACT: dict[InferenceState, dict] = {
    InferenceState.DESCRIPTIVE_ONLY: {
        "allowed_interpretation_level": InterpretationLevel.DESCRIPTIVE_ONLY,
        "conclusion": None,
        "forbidden_inference_flags": [
            "no_p_value",
            "no_causality",
            "no_biological_mechanism",
            "no_hypothesis",
        ],
        "allows_numeric_facts": True,
        "allows_biological_narrative": False,
    },
    InferenceState.LOW_POWER: {
        "allowed_interpretation_level": InterpretationLevel.DESCRIPTIVE_ONLY,
        "conclusion": "no_conclusion",
        "forbidden_inference_flags": [
            "no_causality",
            "no_biological_mechanism",
            "no_significance_claim",
            "no_hypothesis",
        ],
        "allows_numeric_facts": True,
        "allows_biological_narrative": False,
    },
    InferenceState.NOT_SIGNIFICANT: {
        "allowed_interpretation_level": InterpretationLevel.DESCRIPTIVE_ONLY,
        "conclusion": "not_significant",
        "forbidden_inference_flags": [
            "no_causality",
            "no_biological_mechanism",
            "no_significance_claim",
            "no_absence_claim",
        ],
        "allows_numeric_facts": True,
        "allows_biological_narrative": False,
    },
    InferenceState.SIGNIFICANT_INFERENTIAL: {
        "allowed_interpretation_level": InterpretationLevel.INFERENTIAL,
        "conclusion": "significant",
        "forbidden_inference_flags": [
            "no_causality",
            "no_biological_mechanism",
        ],
        "allows_numeric_facts": True,
        "allows_biological_narrative": False,
    },
    InferenceState.BLOCKED: {
        "allowed_interpretation_level": InterpretationLevel.BLOCKED,
        "conclusion": None,
        "forbidden_inference_flags": [
            "no_causality",
            "no_biological_mechanism",
            "no_significance_claim",
            "no_hypothesis",
            "no_numeric_inference",
        ],
        "allows_numeric_facts": False,
        "allows_biological_narrative": False,
    },
}


def _to_float(value, default=None):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n:
        return default
    return n


def assign_inference_state(tool_name: str, result: dict) -> InferenceState:
    if result.get("error"):
        return InferenceState.BLOCKED

    if tool_name in (
        "compare_across_age",
        "senescence_score",
        "find_senescence_markers",
        "get_cluster_annotations",
        "generate_umap",
    ):
        return InferenceState.DESCRIPTIVE_ONLY

    if tool_name == "test_senescence_difference":
        n_samples = result.get("n_samples") or {}
        n_cells = result.get("n_cells") or {}
        n_ref = int(n_samples.get("reference") or 0)
        n_comp = int(n_samples.get("comparison") or 0)
        ref_cells = int(n_cells.get("reference") or 0)
        comp_cells = int(n_cells.get("comparison") or 0)
        p_value = _to_float(result.get("p_value"))
        tier = result.get("inference_tier") or ""

        low_power = (
            tier == "low_power"
            or n_ref < RECOMMENDED_SAMPLES_PER_GROUP
            or n_comp < RECOMMENDED_SAMPLES_PER_GROUP
            or ref_cells < MIN_CELLS_PER_GROUP_INFERENCE
            or comp_cells < MIN_CELLS_PER_GROUP_INFERENCE
            or bool(result.get("warnings"))
        )
        if low_power:
            return InferenceState.LOW_POWER
        if p_value is not None and p_value >= ALPHA:
            return InferenceState.NOT_SIGNIFICANT
        if result.get("significant_at_0.05"):
            return InferenceState.SIGNIFICANT_INFERENTIAL
        return InferenceState.NOT_SIGNIFICANT

    if tool_name == "run_deseq2":
        rows = result.get("results") or []
        sig = [r for r in rows if _to_float(r.get("padj"), 1) < ALPHA]
        n_samples = int(result.get("n_samples") or 0)
        samples_per_age = result.get("samples_per_age") or {}
        low_power = n_samples < 4 or any(
            int(c) < MIN_PSEUDOBULK_SAMPLES_PER_AGE for c in samples_per_age.values()
        )
        if not sig:
            return InferenceState.NOT_SIGNIFICANT
        if low_power:
            return InferenceState.LOW_POWER
        return InferenceState.SIGNIFICANT_INFERENTIAL

    return InferenceState.DESCRIPTIVE_ONLY


def build_state_record(
    tool_name: str,
    result: dict,
    args: Optional[dict] = None,
) -> dict:
    """Attach inference_state block to tool result (replaces loose scientific_validation)."""
    args = args or {}
    state = assign_inference_state(tool_name, result)
    contract = STATE_CONTRACT[state]

    power_reasons = []
    if state == InferenceState.LOW_POWER:
        if tool_name == "test_senescence_difference":
            power_reasons = list(result.get("warnings") or [])
            ns = result.get("n_samples") or {}
            if int(ns.get("reference") or 0) < RECOMMENDED_SAMPLES_PER_GROUP:
                power_reasons.append("few_reference_samples")
            if int(ns.get("comparison") or 0) < RECOMMENDED_SAMPLES_PER_GROUP:
                power_reasons.append("few_comparison_samples")
        elif tool_name == "run_deseq2":
            power_reasons.append("few_pseudobulk_samples")

    record = {
        "state": state.value,
        "state_id": {"DESCRIPTIVE_ONLY": "A", "LOW_POWER": "B", "NOT_SIGNIFICANT": "C",
                     "SIGNIFICANT_INFERENTIAL": "D", "BLOCKED": "E"}[state.value],
        "tool": tool_name,
        "allowed_interpretation_level": contract["allowed_interpretation_level"].value,
        "conclusion": contract["conclusion"],
        "forbidden_inference_flags": list(contract["forbidden_inference_flags"]),
        "allows_biological_narrative": contract["allows_biological_narrative"],
        "power_gate_passed": state not in (InferenceState.LOW_POWER, InferenceState.BLOCKED),
        "power_gate_reasons": power_reasons,
        "statistical_unit": _statistical_unit(tool_name),
    }
    return record


def _statistical_unit(tool_name: str) -> str:
    if tool_name == "test_senescence_difference":
        return "biological_replicate"
    if tool_name == "run_deseq2":
        return "pseudobulk_sample"
    if tool_name == "compare_across_age":
        return "cell"
    return "none"


def apply_inference_state(
    tool_name: str,
    result: Any,
    args: Optional[dict] = None,
) -> Any:
    if not isinstance(result, dict):
        return result
    out = dict(result)
    out["inference_state"] = build_state_record(tool_name, out, args)
    return out
