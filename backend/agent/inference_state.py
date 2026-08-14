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


def _deseq2_group_counts(result: dict) -> list[int]:
    per_group = result.get("samples_per_age") or result.get("samples_per_group") or {}
    return [int(c) for c in per_group.values()]


def _deseq2_n_significant(result: dict) -> int:
    if result.get("n_significant_fdr_0_05") is not None:
        return int(result["n_significant_fdr_0_05"])
    rows = result.get("results") or []
    return sum(1 for r in rows if _to_float(r.get("padj"), 1) < ALPHA)


def _plausibility_suspect(result: dict) -> bool:
    """True when the result-plausibility check (Gate 2) flagged the effect sizes
    as the fingerprint of a technical artifact rather than real biology."""
    plaus = result.get("result_plausibility") or {}
    return plaus.get("verdict") == "suspect"


def _replicate_stability_failed(result: dict) -> bool:
    stability = result.get("replicate_stability") or {}
    return stability.get("verdict") in {
        "unstable", "insufficient_evidence", "assessment_failed"
    }


def _deseq2_low_power(result: dict) -> tuple[bool, list[str]]:
    """Match test_senescence_difference: <3 replicates/group is exploratory only."""
    reasons: list[str] = []
    group_counts = _deseq2_group_counts(result)
    if not group_counts:
        n_total = int(result.get("n_samples") or 0)
        if n_total < RECOMMENDED_SAMPLES_PER_GROUP * 2:
            reasons.append("few_pseudobulk_samples")
        return bool(reasons), reasons

    for count in group_counts:
        if count < MIN_PSEUDOBULK_SAMPLES_PER_AGE:
            reasons.append("insufficient_replicates_per_group")
            break
    for count in group_counts:
        if count < RECOMMENDED_SAMPLES_PER_GROUP:
            reasons.append("few_replicates_per_group")
            break

    for w in (result.get("admissibility_warnings") or []) + (result.get("warnings") or []):
        if "few_replicates" in str(w) and "few_replicates_per_group" not in reasons:
            reasons.append("few_replicates_per_group")

    return bool(reasons), reasons


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
        n_sig = _deseq2_n_significant(result)
        low_power, _ = _deseq2_low_power(result)
        if not n_sig:
            return InferenceState.NOT_SIGNIFICANT
        if low_power:
            return InferenceState.LOW_POWER
        if _plausibility_suspect(result):
            # Statistically significant, but the effect sizes carry the signature
            # of a technical artifact (library-size / low-count imbalance). This is
            # not a valid inferential conclusion — downgrade to descriptive so no
            # finding is licensed, even though the design passed admissibility.
            return InferenceState.DESCRIPTIVE_ONLY
        if _replicate_stability_failed(result):
            return InferenceState.DESCRIPTIVE_ONLY
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
            _, power_reasons = _deseq2_low_power(result)
            power_reasons.extend(result.get("admissibility_warnings") or [])

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
        "validity_flags": _validity_flags(tool_name, result),
    }
    # Validity axis overrides the power axis: an inadmissible inference cannot be
    # licensed to conclude even if a p-value is "significant".
    if record["validity_flags"] and record["allowed_interpretation_level"] == InterpretationLevel.INFERENTIAL.value:
        record["allowed_interpretation_level"] = InterpretationLevel.DESCRIPTIVE_ONLY.value
        record["conclusion"] = None
        record["validity_gate_passed"] = False
    else:
        record["validity_gate_passed"] = not record["validity_flags"]
    return record


def _statistical_unit(tool_name: str) -> str:
    if tool_name == "test_senescence_difference":
        return "biological_replicate"
    if tool_name == "run_deseq2":
        return "pseudobulk_sample"
    if tool_name in ("compare_across_age", "differential_expression"):
        return "cell"
    return "none"


# Tools whose statistical unit is the individual cell. Any *inferential* claim
# built on a cell-unit comparison across biological groups is pseudoreplication.
_CELL_UNIT_TOOLS = ("compare_across_age", "differential_expression")

# Tools that define groups from expression and then test on that same expression
# (leiden clusters -> marker DE). This is circular / double-dipping inference.
_CIRCULAR_INFERENCE_TOOLS = ("differential_expression",)


def _validity_flags(tool_name: str, result: dict) -> list[str]:
    """
    Validity axis (distinct from the power/significance axis).

    Flags encode *admissibility* violations — reasons an inferential claim
    would be statistically invalid regardless of the p-value. The renderer
    uses these to forbid conclusions even when a tool returns a small p.
    """
    flags: list[str] = []

    if tool_name in _CELL_UNIT_TOOLS:
        flags.append("cell_unit_not_inferential")  # pseudoreplication if tested across groups

    if tool_name in _CIRCULAR_INFERENCE_TOOLS:
        flags.append("circular_inference_risk")  # clusters defined on same features tested

    # Result-plausibility (Gate 2): effect sizes look like a technical artifact
    # (implausible fold-changes / near-uniform direction). A significant p-value
    # over an artifact is not a valid conclusion, so this overrides significance.
    if _plausibility_suspect(result):
        flags.append("technical_artifact_risk")

    stability_verdict = (result.get("replicate_stability") or {}).get("verdict")
    if stability_verdict == "unstable":
        flags.append("replicate_instability")
    elif stability_verdict in {"insufficient_evidence", "assessment_failed"}:
        flags.append("replicate_stability_not_established")

    # Uncorrected multiple testing: many per-feature p-values without adjusted p.
    rows = result.get("results") or result.get("top_markers")
    if isinstance(rows, list) and rows:
        has_p = any("pvalue" in r or "p_value" in r or "pvals" in r for r in rows if isinstance(r, dict))
        has_padj = any("padj" in r or "pvals_adj" in r or "p_adj" in r for r in rows if isinstance(r, dict))
        if has_p and not has_padj:
            flags.append("uncorrected_multiple_testing")

    return flags


def apply_inference_state(
    tool_name: str,
    result: Any,
    args: Optional[dict] = None,
) -> Any:
    if not isinstance(result, dict):
        return result
    out = dict(result)
    out["inference_state"] = build_state_record(tool_name, out, args)
    if tool_name in _CIRCULAR_INFERENCE_TOOLS:
        out["analysis_scope"] = "descriptive_marker_discovery"
        out["inferentially_licensed"] = False
        out["validity_flags"] = list(out["inference_state"].get("validity_flags") or [])
    return out
