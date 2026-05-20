import os
import scanpy as sc
import matplotlib.pyplot as plt

from tools.config import OUTPUT_DIR

from tools.gene_utils import (
    SENESCENCE_GENES,
    SENESCENCE_GENES_MOUSE
)

# =========================
# Senescence markers
# =========================

def find_senescence_markers(adata, species: str = "mouse"):
    """
    Check which SenMayo senescence genes are present in the dataset.

    Returns found and missing gene lists.
    Uses pre-cached mouse gene names to avoid API calls at runtime.
    """

    genes = (
        SENESCENCE_GENES_MOUSE
        if species == "mouse"
        else SENESCENCE_GENES
    )

    found = [g for g in genes if g in adata.var_names]
    missing = [g for g in genes if g not in adata.var_names]

    coverage = round(len(found) / len(genes) * 100, 1)
    print(f"SenMayo coverage: {len(found)}/{len(genes)} genes ({coverage}%)")

    return {
        "found_markers": found,
        "missing_markers": missing,
        "coverage_pct": coverage,
        "species": species
    }

# =========================
# Senescence scoring
# =========================

def senescence_score(adata, species: str = "mouse"):
    """
    Score each cell against the SenMayo gene signature.

    Higher score = more senescent phenotype.
    Uses sc.tl.score_genes (Scanpy built-in).
    Saves a UMAP colored by senescence score.

    Returns per-cluster mean scores — the highest scoring
    clusters are your senescent cell populations.
    """

    genes = (
        SENESCENCE_GENES_MOUSE
        if species == "mouse"
        else SENESCENCE_GENES
    )

    # Only use genes present in dataset
    available = [g for g in genes if g in adata.var_names]

    if len(available) == 0:
        return {"error": "No SenMayo genes found in dataset. Check species parameter."}

    print(f"Scoring cells using {len(available)} SenMayo genes...")

    sc.tl.score_genes(
        adata,
        gene_list=available,
        score_name="senescence_score"
    )

    # Only compute UMAP if not already done
    if "X_umap" not in adata.obsm:
        sc.tl.umap(adata)

    # UMAP colored by senescence score
    sc.pl.umap(
        adata,
        color="senescence_score",
        show=False,
        cmap="Reds",
        title="SenMayo Senescence Score"
    )

    filepath = os.path.join(OUTPUT_DIR, "senescence_score.png")
    plt.savefig(filepath, bbox_inches="tight")
    plt.close()

    # Summary statistics
    score_summary = adata.obs["senescence_score"].describe()

    # Per-cluster mean scores — sorted highest first
    cluster_scores = (
        adata.obs
        .groupby("leiden", observed=True)["senescence_score"]
        .mean()
        .sort_values(ascending=False)
    )

    top_cluster = cluster_scores.index[0]

    # Map cluster → most common cell type (if column exists)
    top_celltype = None
    if "cell_ontology_class" in adata.obs.columns:
        cluster_to_celltype = (
            adata.obs
            .groupby("leiden", observed=True)["cell_ontology_class"]
            .agg(lambda x: x.value_counts().index[0])
        )
        top_celltype = cluster_to_celltype[top_cluster]

    print(f"Highest senescence cluster: {top_cluster} "
          f"(mean score: {cluster_scores.iloc[0]:.4f})")

    if top_celltype:
        print(f"Most common cell type in that cluster: {top_celltype}")

    return {
        "top_senescent_cluster": top_cluster,
        "top_senescent_cell_type": top_celltype,
        "genes_used": len(available),
        "total_senmayo_genes": len(genes),
        "mean_score": round(float(score_summary["mean"]), 4),
        "max_score": round(float(score_summary["max"]), 4),
        "cluster_scores": cluster_scores.round(4).to_dict(),
        "plot_path": filepath
    }
