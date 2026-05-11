import scanpy as sc

# Load built-in test dataset
adata = sc.datasets.pbmc68k_reduced()
print("Dataset loaded successfully")
print(f"Shape: {adata.shape}")
print(f"Observations: {adata.obs_names[:5]}")