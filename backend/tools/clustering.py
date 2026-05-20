import scanpy as sc
# =========================
# Clustering
# =========================

def cluster_cells(adata):
    """
    Cluster cells using PCA + neighbor graph + Leiden algorithm.

    Steps:
    1. Find highly variable genes
    2. PCA dimensionality reduction
    3. Build k-nearest neighbor graph
    4. Leiden community detection
    """

    sc.pp.highly_variable_genes(
        adata,
        min_mean=0.0125,
        max_mean=3,
        min_disp=0.5
    )

    sc.pp.pca(adata)
    sc.pp.neighbors(adata)

    sc.tl.leiden(
        adata,
        flavor="igraph",
        n_iterations=2,
        directed=False
    )

    n_clusters = adata.obs["leiden"].nunique()
    print(f"Clustering complete. Found {n_clusters} clusters.")

    return adata