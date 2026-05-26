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
    age_column: str = "age",
    cell_type_column: str = "cell_ontology_class",
    sample_column: str = "sample_id",
    reference_age: str = "3m",
    comparison_age: str = "24m",
    species: str = "mouse",
):
    """
    Compare SenMayo scores between two age groups using Mann-Whitney U on
    per-sample median scores (biological replicates), not individual cells.
    """

    if not cell_type:
        return {"error": "cell_type is required (e.g. 'T cell', 'macrophage')."}

    if age_column not in adata.obs.columns:
        return {
            "error": f"Column '{age_column}' not found. Available: {list(adata.obs.columns)}"
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

    ref = str(reference_age)
    comp = str(comparison_age)

    subset = adata[adata.obs[cell_type_column].astype(str) == resolved_cell_type].copy()

    sample_rows = []
    for sample_id in subset.obs[resolved_sample_col].astype(str).unique():
        cells = subset[subset.obs[resolved_sample_col].astype(str) == sample_id]
        age = str(cells.obs[age_column].iloc[0])
        if age not in (ref, comp):
            continue
        sample_rows.append({
            "sample_id": sample_id,
            "age": age,
            "median_senescence_score": float(cells.obs["senescence_score"].median()),
            "n_cells": int(cells.shape[0]),
        })

    if not sample_rows:
        return {
            "error": (
                f"No samples found for {resolved_cell_type} at ages {ref} or {comp}. "
                f"Available ages: {sorted(subset.obs[age_column].astype(str).unique().tolist())}"
            ),
        }

    ref_scores = [r["median_senescence_score"] for r in sample_rows if r["age"] == ref]
    comp_scores = [r["median_senescence_score"] for r in sample_rows if r["age"] == comp]
    ref_cells = sum(r["n_cells"] for r in sample_rows if r["age"] == ref)
    comp_cells = sum(r["n_cells"] for r in sample_rows if r["age"] == comp)

    warnings = []
    inference_tier = "inferential"

    if len(ref_scores) < MIN_SAMPLES_PER_GROUP or len(comp_scores) < MIN_SAMPLES_PER_GROUP:
        return {
            "error": "Insufficient biological replicates for testing.",
            "cell_type": resolved_cell_type,
            "reference_age": ref,
            "comparison_age": comp,
            "n_samples": {"reference": len(ref_scores), "comparison": len(comp_scores)},
            "n_cells": {"reference": ref_cells, "comparison": comp_cells},
            "sample_column": resolved_sample_col,
            "hint": f"Need at least {MIN_SAMPLES_PER_GROUP} samples per age group.",
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
        "reference_age": ref,
        "comparison_age": comp,
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
