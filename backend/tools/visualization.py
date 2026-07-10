import os
import scanpy as sc
import matplotlib.pyplot as plt

from tools.config import OUTPUT_DIR

# =========================
# UMAP generation
# =========================

def generate_umap(adata, filename="umap.png"):
    """
    Generate a 2D UMAP colored by **cell type** when the dataset has cell-type
    annotations (far more meaningful than cluster numbers); falls back to
    Leiden/Louvain clusters otherwise.

    Saves plot to outputs/ directory. Returns path to saved image.
    """

    # Only compute UMAP if not already done
    if "X_umap" not in adata.obsm:
        sc.tl.umap(adata)

    # Prefer biological cell-type labels; fall back to clusters.
    profile = adata.uns.get("dataset_profile") or {}
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    candidates = [ct_col, "cell_ontology_class", "cell_type", "leiden", "louvain"]
    color = next(
        (c for c in candidates
         if c in adata.obs.columns and adata.obs[c].astype(str).nunique() > 1),
        None,
    )
    if color is None:  # only one category (or none) — use whatever exists
        color = next((c for c in candidates if c in adata.obs.columns), None)

    nice = {
        "cell_ontology_class": "cell type", "cell_type": "cell type",
        "leiden": "cluster", "louvain": "cluster",
    }.get(color, str(color))

    sc.pl.umap(
        adata, color=color, show=False, frameon=True,
        legend_loc="right margin",
        title=f"UMAP colored by {nice}",
    )

    filepath = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(filepath, bbox_inches="tight", dpi=150)
    plt.close()

    print(f"UMAP saved to: {filepath} (colored by {color})")

    return filepath
