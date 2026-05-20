import scanpy as sc
# =========================
# Quality control
# =========================

def quality_control(adata, species: str = "mouse"):
    """
    Remove low-quality cells and genes.

    Filters:
    - Cells with fewer than 200 detected genes (likely empty droplets)
    - Genes detected in fewer than 3 cells (likely noise)

    Species parameter passed through for downstream
    gene name normalization consistency.
    """

    print(f"Before QC: {adata.shape[0]} cells, {adata.shape[1]} genes")
    print(f"Species: {species}")

    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)

    print(f"After QC:  {adata.shape[0]} cells, {adata.shape[1]} genes")

    return adata, species

# =========================
# Normalization
# =========================

def normalize(adata):
    """
    Normalize counts per cell and apply log transform.

    Normalizes each cell to 10,000 total counts,
    then applies log1p to stabilize variance.
    """

    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    adata.raw = adata.copy()  # Save raw counts for later use
    print("Normalization complete.")

    return adata
