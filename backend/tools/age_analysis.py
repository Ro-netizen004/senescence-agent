# =========================
# Age comparison
# =========================

import os
import scanpy as sc
import matplotlib.pyplot as plt
from tools.senescence import senescence_score as _senescence_score


def compare_across_age(
    adata,
    age_column: str = "age",
    cell_type_column: str = "cell_ontology_class",
    species: str = "mouse",
):
    """
    Compare senescence trends across age groups and cell types.
    """

    # =========================
    # Validate columns
    # =========================

    if age_column not in adata.obs.columns:
        return {
            "error": f"Column '{age_column}' not found. Available: {adata.obs.columns.tolist()}"
        }

    if cell_type_column not in adata.obs.columns:
        return {
            "error": f"Column '{cell_type_column}' not found. Available: {adata.obs.columns.tolist()}"
        }

    # =========================
    # Normalize + log transform
    # =========================

    if "log1p" not in adata.uns:
        print("Running normalization + log1p...")
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)

    # =========================
    # Run senescence scoring
    # =========================

    if "senescence_score" not in adata.obs.columns:
        print("Running senescence scoring...")
        _senescence_score(adata, species)

    # =========================
    # Metadata
    # =========================

    ages = sorted(adata.obs[age_column].astype(str).unique().tolist())

    age_counts = (
        adata.obs[age_column]
        .astype(str)
        .value_counts()
        .sort_index()
        .to_dict()
    )

    result = {
        "age_groups": ages,
        "age_counts": age_counts,
        "total_cells": adata.shape[0],
    }

    print(f"Age groups found: {ages}")

    # =========================
    # Cell type proportions
    # =========================

    cross_tab = (
        adata.obs
        .groupby([age_column, cell_type_column], observed=True)
        .size()
        .unstack(fill_value=0)
    )

    proportions = cross_tab.div(cross_tab.sum(axis=1), axis=0)

    result["cell_type_proportions"] = proportions.round(3).to_dict()

    result["cell_types"] = sorted(
        adata.obs[cell_type_column].astype(str).unique().tolist()
    )

    # =========================
    # GLOBAL senescence (DESCRIPTIVE ONLY)
    # =========================

    global_senescence = (
        adata.obs
        .groupby(age_column, observed=True)["senescence_score"]
        .mean()
        .round(4)
        .to_dict()
    )

    result["global_senescence_by_age"] = global_senescence

    result["global_note"] = (
        "Global senescence is descriptive only and is confounded by cell-type composition. "
        "Do NOT use it for ranking biological aging."
    )

    print("\nGlobal senescence by age:")
    print(global_senescence)

    # =========================
    # Cell-type specific analysis (PRIMARY RESULT)
    # =========================

    celltype_age_scores = {}

    print("\nCell-type specific senescence trends:")

    for cell_type in sorted(adata.obs[cell_type_column].astype(str).unique()):

        subset = adata[
            adata.obs[cell_type_column].astype(str) == cell_type
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

        celltype_age_scores[cell_type] = age_scores

        print(f"\n{cell_type}")
        print(age_scores)

    result["senescence_by_celltype_and_age"] = celltype_age_scores

    # =========================
    # Most senescent per cell type (OK)
    # =========================

    most_senescent_per_celltype = {}

    for cell_type, scores in celltype_age_scores.items():
        if not scores:
            continue

        top_age = max(scores, key=scores.get)

        most_senescent_per_celltype[cell_type] = {
            "age": top_age,
            "score": scores[top_age]
        }

    result["most_senescent_per_celltype"] = most_senescent_per_celltype

    # =========================
    # Plots
    # =========================

    os.makedirs("plots", exist_ok=True)

    # ---- Age distribution ----
    try:
        plt.figure(figsize=(6, 4))

        adata.obs[age_column].astype(str).value_counts().sort_index().plot(kind="bar")

        plt.title("Cell Distribution Across Age Groups")
        plt.xlabel("Age Group")
        plt.ylabel("Number of Cells")
        plt.tight_layout()

        path = "plots/age_distribution.png"
        plt.savefig(path)
        plt.close()

        result["age_distribution_plot"] = path

    except Exception as e:
        print(f"Age plot error: {e}")

    # ---- Violin plot ----
    try:
        sc.pl.violin(
            adata,
            keys="senescence_score",
            groupby=age_column,
            stripplot=False,
            show=False
        )

        path = "plots/senescence_violin.png"
        plt.savefig(path, bbox_inches="tight")
        plt.close()

        result["senescence_violin_plot"] = path

    except Exception as e:
        print(f"Violin plot error: {e}")

    # =========================
    # Summary
    # =========================

    print("\n=========================")
    print("AGE ANALYSIS COMPLETE")
    print("=========================")

    print("\nGlobal senescence (descriptive only):")
    print(global_senescence)

    return result