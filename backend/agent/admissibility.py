"""
Admissibility pre-check (Gate 1 of 2).

Runs BEFORE an inferential tool executes. Answers: given the data's *design*,
is this inference even valid to attempt? Blocks inadmissible inferences up front
(pseudoreplication, insufficient replicates, confounded contrast, circular
inference) so an invalid claim can never be computed in the first place.

This is deterministic and LLM-free by design — the LLM may propose an intent,
but it cannot make an inadmissible inference admissible.

Companion to the justification post-check in inference_state.build_state_record.
"""

from __future__ import annotations

from typing import Optional

# Minimum biological replicates per group for any variance estimate to exist.
MIN_ADMISSIBLE_REPLICATES = 2
RECOMMENDED_REPLICATES = 3

# Group-comparison tools that require biological replicates to be admissible.
_REPLICATE_INFERENCE_TOOLS = ("test_senescence_difference", "run_deseq2")

# Per-cell cluster-marker DE: groups are defined on the same expression later
# tested — circular / double-dipping. Admissible only as descriptive discovery.
_CIRCULAR_TOOLS = ("differential_expression",)

# Columns that commonly confound an age/condition contrast if perfectly separated.
_CANDIDATE_CONFOUNDERS = ("batch", "sex", "10x_chemistry", "method", "plate", "donor_sex")


def _profile(adata) -> dict:
    return adata.uns.get("dataset_profile") or {}


def _resolve_sample_column(adata) -> Optional[str]:
    try:
        from tools.build_pseudobulk import _get_sample_column
        return _get_sample_column(adata, (_profile(adata)).get("sample_column") or "sample_id")
    except Exception:
        return None


def _sample_level_frame(adata, sample_col, group_col, extra_cols=None):
    """One row per sample: its group value (and any extra covariates)."""
    cols = [sample_col, group_col] + [c for c in (extra_cols or []) if c in adata.obs.columns]
    df = adata.obs[cols].astype(str).drop_duplicates(subset=[sample_col])
    return df


def _replicates_per_group(adata, sample_col, group_col, groups) -> dict:
    df = _sample_level_frame(adata, sample_col, group_col)
    counts = {}
    for g in groups:
        counts[g] = int((df[group_col] == str(g)).sum())
    return counts


def _confounded_with(adata, sample_col, group_col, groups) -> list[str]:
    """
    Return candidate confounder columns that PERFECTLY separate the two groups
    at the sample level (each confounder value appears in only one group).
    """
    hits = []
    present = [c for c in _CANDIDATE_CONFOUNDERS if c in adata.obs.columns]
    if not present:
        return hits
    df = _sample_level_frame(adata, sample_col, group_col, present)
    df = df[df[group_col].isin([str(g) for g in groups])]
    for c in present:
        # For each confounder value, which groups does it appear in?
        by_val = df.groupby(c)[group_col].nunique()
        # If every confounder value maps to exactly one group AND there is >1 value,
        # the confounder perfectly separates the groups.
        if len(by_val) > 1 and (by_val == 1).all():
            hits.append(c)
    return hits


def check_admissibility(tool_name: str, args: dict, adata) -> dict:
    """
    Returns:
      {
        "admissible": bool,
        "blocked_reasons": [...],   # each blocks the inference
        "warnings": [...],          # non-blocking, surfaced to user
        "checks": {...},            # what was inspected (for transparency/paper)
      }
    """
    args = args or {}
    reasons: list[str] = []
    warnings: list[str] = []
    checks: dict = {"tool": tool_name}

    prof = _profile(adata)
    age_col = args.get("age_column") or prof.get("age_column") or "age"
    ct_col = args.get("cell_type_column") or prof.get("cell_type_column") or "cell_ontology_class"

    # ── Circular inference (per-cell cluster-marker DE) ──────────────────
    if tool_name in _CIRCULAR_TOOLS:
        warnings.append(
            "circular_inference: clusters are defined on the same expression being "
            "tested; markers are admissible as descriptive discovery only, not as "
            "inferential differential expression."
        )
        checks["circular_inference"] = True

    # ── Replicate-based group comparisons ────────────────────────────────
    if tool_name in _REPLICATE_INFERENCE_TOOLS:
        sample_col = _resolve_sample_column(adata)
        checks["sample_column"] = sample_col

        if sample_col is None:
            reasons.append(
                "no_replicate_unit: no sample/donor column found, so the statistical "
                "unit is the cell. A between-group test would be pseudoreplication."
            )
            return _finish(reasons, warnings, checks)

        if age_col not in adata.obs.columns:
            reasons.append(f"missing_group_column: '{age_col}' not in dataset.")
            return _finish(reasons, warnings, checks)

        ref = str(args.get("reference_age", "3m"))
        comp = str(args.get("comparison_age", "24m"))
        groups = [ref, comp]
        checks["contrast"] = {"reference": ref, "comparison": comp, "group_column": age_col}

        # Restrict to the requested cell type if the tool uses one
        scoped = adata
        cell_type = args.get("cell_type")
        if cell_type and ct_col in adata.obs.columns:
            try:
                from tools.age_analysis import _resolve_cell_type
                available = sorted(adata.obs[ct_col].astype(str).unique().tolist())
                resolved = _resolve_cell_type(cell_type, available)
                if resolved:
                    scoped = adata[adata.obs[ct_col].astype(str) == resolved]
                    checks["cell_type"] = resolved
            except Exception:
                pass

        reps = _replicates_per_group(scoped, sample_col, age_col, groups)
        checks["replicates_per_group"] = reps

        low = [g for g, n in reps.items() if n < MIN_ADMISSIBLE_REPLICATES]
        if low:
            reasons.append(
                f"insufficient_replicates: groups {low} have < {MIN_ADMISSIBLE_REPLICATES} "
                f"biological replicates (counts={reps}). No between-replicate variance can "
                f"be estimated; a per-cell test here would be pseudoreplication."
            )

        few = [g for g, n in reps.items() if MIN_ADMISSIBLE_REPLICATES <= n < RECOMMENDED_REPLICATES]
        if few:
            warnings.append(
                f"few_replicates: groups {few} have < {RECOMMENDED_REPLICATES} replicates "
                f"(counts={reps}); the inference is admissible but low-powered."
            )

        confounders = _confounded_with(scoped, sample_col, age_col, groups)
        if confounders:
            checks["confounded_with"] = confounders
            warnings.append(
                f"confounded_contrast: the contrast is perfectly separated by {confounders}; "
                f"any difference cannot be attributed to {age_col} rather than {confounders}."
            )

    return _finish(reasons, warnings, checks)


def _finish(reasons, warnings, checks) -> dict:
    return {
        "admissible": len(reasons) == 0,
        "blocked_reasons": reasons,
        "warnings": warnings,
        "checks": checks,
    }


def admissibility_block_result(tool_name: str, admissibility: dict) -> dict:
    """
    Build a BLOCKED-shaped tool result when a pre-check fails, so the existing
    inference-state machine + renderer refuse it without running the tool.
    """
    return {
        "error": "inadmissible_inference",
        "tool": tool_name,
        "admissibility": admissibility,
        "message": (
            "This inference is inadmissible given the data design and was not run. "
            + " ".join(admissibility.get("blocked_reasons", []))
        ),
    }
