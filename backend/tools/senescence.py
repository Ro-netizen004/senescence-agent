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
        score_name="senescence_score",
        use_raw=False,  # always use adata.X (log-normalized), never adata.raw
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

    cluster_scores = (
        adata.obs
        .groupby("leiden", observed=True)["senescence_score"]
        .mean()
        .sort_values(ascending=False)
    )

    top_cluster = cluster_scores.index[0]

    # Map ALL clusters → most common cell type. Prefer real annotations; if the
    # dataset has none, fall back to marker-based predicted cell types so the
    # per-cluster scores read as biology instead of bare cluster numbers.
    from tools.cell_type_annotation import ensure_predicted_cell_types, PREDICTED_COL
    ensure_predicted_cell_types(adata, species)

    label_col = None
    if "cell_ontology_class" in adata.obs.columns:
        label_col = "cell_ontology_class"
    elif PREDICTED_COL in adata.obs.columns:
        label_col = PREDICTED_COL

    cluster_to_celltype = {}
    if label_col is not None:
        cluster_to_celltype = (
            adata.obs
            .groupby("leiden", observed=True)[label_col]
            .agg(lambda x: x.value_counts().index[0])
            .to_dict()
        )

    
    top_celltype = cluster_to_celltype.get(top_cluster)

    # Build labeled scores dict: {"12 (mesangial cell)": 0.2357, ...}
    labeled_scores = {
        f"{cluster} ({cluster_to_celltype[cluster]})" if cluster in cluster_to_celltype else str(cluster): round(float(score), 4)
        for cluster, score in cluster_scores.items()
    }

    return {
        "top_senescent_cluster": top_cluster,
        "top_senescent_cell_type": top_celltype,
        "genes_used": len(available),
        "total_senmayo_genes": len(genes),
        "mean_score": round(float(score_summary["mean"]), 4),
        "max_score": round(float(score_summary["max"]), 4),
        "cluster_scores": labeled_scores,  # ← now all clusters have cell type names
        "plot_path": filepath
    }

def get_cluster_annotations(adata, species: str = "mouse") -> dict:
    """
    Return the dominant cell type per Leiden cluster plus the full per-cluster
    cell-type distribution.

    When the dataset ships real annotations (``cell_ontology_class``) those are
    used. When it does not, cell types are **predicted** from cluster marker
    genes (deterministic, descriptive-only) so the clusters get biological names
    instead of bare numbers. Predicted results carry ``predicted=True`` plus the
    supporting marker genes and a confidence per cluster.
    """

    if "leiden" not in adata.obs.columns:
        return {"error": "No leiden clustering found. Run pipeline first."}

    # No real labels → predict from markers.
    if "cell_ontology_class" not in adata.obs.columns:
        from tools.cell_type_annotation import annotate_clusters_by_markers, PREDICTED_COL

        ann = annotate_clusters_by_markers(adata, species)
        if ann.get("error"):
            return ann

        # Provide the same distribution shape callers expect (trivial here: each
        # cluster maps to a single predicted type at 100%).
        distribution = {
            cid: {label: 1.0} for cid, label in ann["cluster_annotations"].items()
        }
        ann["cluster_distributions"] = distribution
        return ann

    dominant = {}
    distribution = {}

    # iterate cluster by cluster (SAFE, NO PANDAS TO_DICT TRICKS)
    for cluster in adata.obs["leiden"].astype(str).unique():

        subset = adata.obs[adata.obs["leiden"].astype(str) == cluster]

        # ---- dominant cell type ----
        vc = subset["cell_ontology_class"].astype(str).value_counts()

        if len(vc) == 0:
            continue

        dominant[str(cluster)] = str(vc.index[0])

        # ---- distribution (explicit loop = SAFE FOR GEMINI) ----
        total = float(vc.sum())

        dist = {}
        for cell_type, count in vc.items():
            dist[str(cell_type)] = round(float(count) / total, 3)

        distribution[str(cluster)] = dist

    return {
        "cluster_annotations": dominant,
        "cluster_distributions": distribution,
        "total_clusters": len(dominant),
        "predicted": False,
        "method": "dataset_labels",
    }