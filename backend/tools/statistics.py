"""
Sample-level statistical tests for SenMayo senescence scores.

IMPORTANT: Tests use one value per biological replicate (mouse/sample), NOT per cell.
Cell-level Mann-Whitney would inflate significance and is intentionally not offered.
"""

from typing import Optional

import numpy as np
from scipy.stats import mannwhitneyu

from tools.age_analysis import _resolve_cell_type
from tools.build_pseudobulk import _get_sample_column
from tools.senescence import senescence_score as _senescence_score

MIN_SAMPLES_PER_GROUP = 2
RECOMMENDED_SAMPLES_PER_GROUP = 3
MIN_CELLS_WARNING = 20


def test_senescence_difference(
    adata,
    cell_type: str,
    group_column: str = "age",
    cell_type_column: str = "cell_ontology_class",
    sample_column: str = "sample_id",
    reference_group: str = None,
    comparison_group: str = None,
    species: str = "mouse",
    age_column: str = None,
    reference_age: str = None,
    comparison_age: str = None,
):
    """
    Compare SenMayo scores between two groups of a grouping variable (age,
    condition, treatment, ...) using Mann-Whitney U on per-sample median scores
    (biological replicates), not individual cells.

    Back-compat: ``age_column`` / ``reference_age`` / ``comparison_age`` alias
    ``group_column`` / ``reference_group`` / ``comparison_group``.
    """

    group_column = age_column or group_column
    reference_group = reference_group or reference_age
    comparison_group = comparison_group or comparison_age

    if not cell_type:
        return {"error": "cell_type is required (e.g. 'T cell', 'macrophage')."}

    if not reference_group or not comparison_group:
        return {
            "error": (
                f"Two groups to compare are required (reference_group and comparison_group) "
                f"for grouping variable '{group_column}'."
            )
        }

    if group_column not in adata.obs.columns:
        return {
            "error": f"Column '{group_column}' not found. Available: {list(adata.obs.columns)}"
        }

    if cell_type_column not in adata.obs.columns:
        return {
            "error": f"Column '{cell_type_column}' not found. Available: {list(adata.obs.columns)}"
        }

    try:
        resolved_sample_col = _get_sample_column(adata, sample_column)
    except ValueError as e:
        return {
            "error": str(e),
            "hint": (
                "Statistical testing requires a sample/donor column (sample_id, mouse.id, or mouse_id). "
                "Use compare_across_age for descriptive cell-level medians only."
            ),
        }

    available_types = sorted(adata.obs[cell_type_column].astype(str).unique().tolist())
    resolved_cell_type = _resolve_cell_type(cell_type, available_types)
    if not resolved_cell_type:
        return {
            "error": f"Cell type '{cell_type}' not found. Available: {available_types}"
        }

    if "senescence_score" not in adata.obs.columns:
        _senescence_score(adata, species)

    ref = str(reference_group)
    comp = str(comparison_group)

    subset = adata[adata.obs[cell_type_column].astype(str) == resolved_cell_type].copy()

    sample_rows = []
    for sample_id in subset.obs[resolved_sample_col].astype(str).unique():
        cells = subset[subset.obs[resolved_sample_col].astype(str) == sample_id]
        grp = str(cells.obs[group_column].iloc[0])
        if grp not in (ref, comp):
            continue
        sample_rows.append({
            "sample_id": sample_id,
            "group": grp,
            "median_senescence_score": float(cells.obs["senescence_score"].median()),
            "n_cells": int(cells.shape[0]),
        })

    if not sample_rows:
        return {
            "error": (
                f"No samples found for {resolved_cell_type} in {group_column} groups {ref} or {comp}. "
                f"Available groups: {sorted(subset.obs[group_column].astype(str).unique().tolist())}"
            ),
        }

    ref_scores = [r["median_senescence_score"] for r in sample_rows if r["group"] == ref]
    comp_scores = [r["median_senescence_score"] for r in sample_rows if r["group"] == comp]
    ref_cells = sum(r["n_cells"] for r in sample_rows if r["group"] == ref)
    comp_cells = sum(r["n_cells"] for r in sample_rows if r["group"] == comp)

    warnings = []
    inference_tier = "inferential"

    if len(ref_scores) < MIN_SAMPLES_PER_GROUP or len(comp_scores) < MIN_SAMPLES_PER_GROUP:
        return {
            "error": "Insufficient biological replicates for testing.",
            "cell_type": resolved_cell_type,
            "group_column": group_column,
            "reference_group": ref,
            "comparison_group": comp,
            "reference_age": ref,       # legacy alias
            "comparison_age": comp,     # legacy alias
            "n_samples": {"reference": len(ref_scores), "comparison": len(comp_scores)},
            "n_cells": {"reference": ref_cells, "comparison": comp_cells},
            "sample_column": resolved_sample_col,
            "hint": f"Need at least {MIN_SAMPLES_PER_GROUP} samples per group.",
        }

    if (
        len(ref_scores) < RECOMMENDED_SAMPLES_PER_GROUP
        or len(comp_scores) < RECOMMENDED_SAMPLES_PER_GROUP
    ):
        warnings.append(
            f"Few biological replicates (reference n={len(ref_scores)}, comparison n={len(comp_scores)}). "
            f"p-values are unreliable with n < {RECOMMENDED_SAMPLES_PER_GROUP} per group."
        )
        inference_tier = "low_power"

    if ref_cells < MIN_CELLS_WARNING or comp_cells < MIN_CELLS_WARNING:
        warnings.append(
            f"Low cell counts (reference {ref_cells}, comparison {comp_cells} cells). "
            "Per-sample medians may be unstable."
        )
        if inference_tier == "inferential":
            inference_tier = "low_power"

    stat, p_value = mannwhitneyu(comp_scores, ref_scores, alternative="two-sided")

    ref_median = float(np.median(ref_scores))
    comp_median = float(np.median(comp_scores))
    effect_size = comp_median - ref_median

    return {
        "status": "ok",
        "test": "mannwhitneyu",
        "unit": "biological_replicate",
        "aggregation": "median_senescence_score_per_sample",
        "cell_type": resolved_cell_type,
        "group_column": group_column,
        "reference_group": ref,
        "comparison_group": comp,
        "reference_age": ref,       # legacy alias
        "comparison_age": comp,     # legacy alias
        "sample_column": resolved_sample_col,
        "n_samples": {
            "reference": len(ref_scores),
            "comparison": len(comp_scores),
        },
        "n_cells": {
            "reference": ref_cells,
            "comparison": comp_cells,
        },
        "sample_level_scores": {
            "reference": ref_scores,
            "comparison": comp_scores,
        },
        "median_score_reference": ref_median,
        "median_score_comparison": comp_median,
        "effect_size": round(effect_size, 4),
        "u_statistic": float(stat),
        "p_value": float(p_value),
        "significant_at_0.05": bool(p_value < 0.05),
        "inference_tier": inference_tier,
        "warnings": warnings,
        "statistical_unit_label": "biological_replicate",
        "aggregation_method": "median_senescence_score_per_sample",
    }
