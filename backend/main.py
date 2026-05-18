import scanpy as sc
from tools.scanpy_tools import (
    quality_control,
    normalize,
    cluster_cells,
    generate_umap,
    find_senescence_markers
)

def main():
    print("Loading dataset...")

    adata = sc.datasets.pbmc3k()

    print("Initial shape:", adata.shape)

    adata = quality_control(adata)
    print("After QC:", adata.shape)

    adata = normalize(adata)

    adata = cluster_cells(adata)

    print("Clusters:")
    print(adata.obs["leiden"].value_counts())

    umap_path = generate_umap(adata)
    print("UMAP saved at:", umap_path)

    result = find_senescence_markers(adata)

    print("Found:", result["found_markers"])
    print("Missing:", result["missing_markers"])

if __name__ == "__main__":
    main()