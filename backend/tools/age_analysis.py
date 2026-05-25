# =========================
# Age comparison
# =========================

import os
import re
from typing import Optional, Tuple

import matplotlib.pyplot as plt
import scanpy as sc

from tools.config import OUTPUT_DIR
from tools.senescence import senescence_score as _senescence_score


def _resolve_cell_type(requested: str, available: list) -> Optional[str]:
    req = requested.strip()
    if req in available:
        return req

    lower_map = {a.lower(): a for a in available}
    key = req.lower()
    if key in lower_map:
        return lower_map[key]

    if key.endswith("s") and key[:-1] in lower_map:
        return lower_map[key[:-1]]
    if key + "s" in lower_map:
        return lower_map[key + "s"]

    return None


def _resolve_age_contrast(
    available_ages: list,
    reference_age: Optional[str] = None,
    comparison_age: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Resolve two age groups for contrast. Returns (reference, comparison, error).
    """
    available = [str(a) for a in available_ages]

    if reference_age and comparison_age:
        ref, comp = str(reference_age), str(comparison_age)
        missing = [a for a in (ref, comp) if a not in available]
        if missing:
            return None, None, (
                f"Age group(s) not found: {missing}. Available: {available}"
            )
        return ref, comp, None

    return None, None, None


def _plot_suffix(cell_type: Optional[str], age_suffix: str = "") -> str:
    parts = []
    if cell_type:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", cell_type.strip().lower()).strip("_")
        if slug:
            parts.append(slug)
    if age_suffix:
        parts.append(age_suffix)
    return f"_{'_'.join(parts)}" if parts else ""


def compare_across_age(
    adata,
    age_column: str = "age",
    cell_type_column: str = "cell_ontology_class",
    species: str = "mouse",
    cell_type: Optional[str] = None,
    reference_age: Optional[str] = None,
    comparison_age: Optional[str] = None,
):
    """
    Compare senescence trends across age groups.

    Optional cell_type restricts to one population.
    reference_age / comparison_age restrict to a two-group contrast (e.g. 3m vs 24m).
    """

    if age_column not in adata.obs.columns:
        return {
            "error": f"Column '{age_column}' not found. Available: {adata.obs.columns.tolist()}"
        }

    if cell_type_column not in adata.obs.columns:
        return {
            "error": f"Column '{cell_type_column}' not found. Available: {adata.obs.columns.tolist()}"
        }

    if "senescence_score" not in adata.obs.columns:
        print("Running senescence scoring...")
        _senescence_score(adata, species)

    available_types = sorted(
        adata.obs[cell_type_column].astype(str).unique().tolist()
    )

    resolved_cell_type = None
    if cell_type:
        resolved_cell_type = _resolve_cell_type(cell_type, available_types)
        if not resolved_cell_type:
            return {
                "error": (
                    f"Cell type '{cell_type}' not found. "
                    f"Available: {available_types}"
                )
            }

    analysis = adata
    if resolved_cell_type:
        analysis = adata[
            adata.obs[cell_type_column].astype(str) == resolved_cell_type
        ].copy()
        if analysis.shape[0] < 20:
            return {
                "error": (
                    f"Only {analysis.shape[0]} cells for '{resolved_cell_type}'. "
                    "Need at least 20 for age comparison."
                )
            }

    all_ages = sorted(analysis.obs[age_column].astype(str).unique().tolist())
    ref_age, comp_age, contrast_err = _resolve_age_contrast(
        all_ages, reference_age, comparison_age
    )
    if contrast_err:
        return {"error": contrast_err}

    age_suffix = ""
    if ref_age and comp_age:
        analysis = analysis[
            analysis.obs[age_column].astype(str).isin([ref_age, comp_age])
        ].copy()
        age_suffix = re.sub(r"[^a-zA-Z0-9]+", "", f"{ref_age}_vs_{comp_age}")
        if analysis.shape[0] < 20:
            return {"error": "Too few cells after age contrast filter."}

    ages = sorted(analysis.obs[age_column].astype(str).unique().tolist())

    age_counts = (
        analysis.obs[age_column]
        .astype(str)
        .value_counts()
        .sort_index()
        .to_dict()
    )

    result = {
        "age_groups": ages,
        "age_counts": age_counts,
        "total_cells": analysis.shape[0],
        "cell_types": available_types,
    }

    if ref_age and comp_age:
        result["age_contrast"] = {
            "reference_age": ref_age,
            "comparison_age": comp_age,
            "note": (
                f"Contrast {comp_age} vs {ref_age}: higher senescence scores in "
                f"{comp_age} indicate stronger signal in the older/comparison group."
            ),
        }

    if resolved_cell_type:
        result["filtered_cell_type"] = resolved_cell_type
        result["dataset_total_cells"] = adata.shape[0]

    if not resolved_cell_type:
        cross_tab = (
            adata.obs
            .groupby([age_column, cell_type_column], observed=True)
            .size()
            .unstack(fill_value=0)
        )
        proportions = cross_tab.div(cross_tab.sum(axis=1), axis=0)
        result["cell_type_proportions"] = proportions.round(3).to_dict()

    senescence_by_age = (
        analysis.obs
        .groupby(age_column, observed=True)["senescence_score"]
        .median()
        .round(4)
        .to_dict()
    )

    if resolved_cell_type:
        result["senescence_by_age"] = senescence_by_age
        result["analysis_note"] = (
            f"Results are for '{resolved_cell_type}' only "
            f"({analysis.shape[0]} of {adata.shape[0]} cells)."
        )
    else:
        result["global_senescence_by_age"] = (
            analysis.obs
            .groupby(age_column, observed=True)["senescence_score"]
            .mean()
            .round(4)
            .to_dict()
        )
        result["global_note"] = (
            "Global senescence is descriptive only and is confounded by cell-type composition. "
            "Do NOT use it for ranking biological aging."
        )

    cell_types_to_analyze = (
        [resolved_cell_type] if resolved_cell_type else available_types
    )

    celltype_age_scores = {}
    for ct in cell_types_to_analyze:
        subset = analysis if resolved_cell_type else adata[
            adata.obs[cell_type_column].astype(str) == ct
        ]
        if ref_age and comp_age and not resolved_cell_type:
            subset = subset[
                subset.obs[age_column].astype(str).isin([ref_age, comp_age])
            ]

        if subset.shape[0] < 20:
            continue

        age_scores = (
            subset.obs
            .groupby(age_column, observed=True)["senescence_score"]
            .median()
            .round(4)
            .to_dict()
        )
        celltype_age_scores[ct] = age_scores

    result["senescence_by_celltype_and_age"] = celltype_age_scores

    most_senescent_per_celltype = {}
    for ct, scores in celltype_age_scores.items():
        if not scores:
            continue
        top_age = max(scores, key=scores.get)
        most_senescent_per_celltype[ct] = {"age": top_age, "score": scores[top_age]}

    result["most_senescent_per_celltype"] = most_senescent_per_celltype

    suffix = _plot_suffix(resolved_cell_type, age_suffix)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        plt.figure(figsize=(6, 4))
        analysis.obs[age_column].astype(str).value_counts().sort_index().plot(kind="bar")
        title = "Cell Distribution Across Age Groups"
        if resolved_cell_type:
            title = f"{resolved_cell_type}: cells per age group"
        if ref_age and comp_age:
            title += f" ({ref_age} vs {comp_age})"
        plt.title(title)
        plt.xlabel("Age Group")
        plt.ylabel("Number of Cells")
        plt.tight_layout()
        path = os.path.join(OUTPUT_DIR, f"age_distribution{suffix}.png")
        plt.savefig(path)
        plt.close()
        result["age_distribution_plot"] = path
    except Exception as e:
        print(f"Age plot error: {e}")

    try:
        sc.pl.violin(
            analysis,
            keys="senescence_score",
            groupby=age_column,
            stripplot=False,
            show=False,
        )
        path = os.path.join(OUTPUT_DIR, f"senescence_violin{suffix}.png")
        plt.savefig(path, bbox_inches="tight")
        plt.close()
        result["senescence_violin_plot"] = path
    except Exception as e:
        print(f"Violin plot error: {e}")

    return result
