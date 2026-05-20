# =========================
# Age comparison
# =========================
import matplotlib.pyplot as plt
import os

def compare_across_age(
    adata,
    age_column: str = "age",
    cell_type_column: str = "cell_ontology_class"
):
    if age_column not in adata.obs.columns:
        return {"error": f"Column '{age_column}' not found. "
                         f"Available: {adata.obs.columns.tolist()}"}

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
        "total_cells": adata.shape[0]
    }

    # Cell type proportions per age group
    if cell_type_column in adata.obs.columns:
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

    # Senescence score trend across age
    # Only available if senescence_score was called first
    if "senescence_score" in adata.obs.columns:
        age_senescence = (
            adata.obs
            .groupby(age_column, observed=True)["senescence_score"]
            .mean()
            .sort_index()
            .round(4)
            .to_dict()
        )
        result["senescence_by_age"] = age_senescence

        # Find age group with highest senescence
        top_age = max(age_senescence, key=age_senescence.get)
        result["most_senescent_age"] = top_age

        print(f"Senescence by age: {age_senescence}")
        print(f"Most senescent age group: {top_age}")

    print(f"Age groups found: {ages}")

        # =========================
    # Plot: age distribution
    # =========================
    plot_path = None

    try:
        plt.figure()

        adata.obs[age_column].astype(str).value_counts().sort_index().plot(kind="bar")

        plt.title("Cell Distribution Across Age Groups")
        plt.xlabel("Age group")
        plt.ylabel("Number of cells")
        plt.tight_layout()

        os.makedirs("plots", exist_ok=True)
        plot_path = f"plots/age_distribution.png"
        plt.savefig(plot_path)
        plt.close()

        result["plot_path"] = plot_path

    except Exception as e:
        print(f"Plot error: {e}")

    return result
