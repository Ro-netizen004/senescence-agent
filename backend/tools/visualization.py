import os
import scanpy as sc
import matplotlib.pyplot as plt

from tools.config import OUTPUT_DIR

# =========================
# UMAP generation
# =========================

def generate_umap(adata, filename="umap.png"):
    """
    Generate 2D UMAP visualization colored by cluster.

    Saves plot to outputs/ directory.
    Returns path to saved image.
    """

    # Only compute UMAP if not already done
    if "X_umap" not in adata.obsm:
        sc.tl.umap(adata)

    sc.pl.umap(adata, color="leiden", show=False)

    filepath = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(filepath, bbox_inches="tight")
    plt.close()

    print(f"UMAP saved to: {filepath}")

    return filepath
