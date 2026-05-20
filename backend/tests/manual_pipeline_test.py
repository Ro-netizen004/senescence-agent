import scanpy as sc

from tools.dataset_loader import load_kidney_dataset

from tools.preprocessing import (
    quality_control,
    normalize
)

from tools.clustering import (
    cluster_cells
)

from tools.visualization import (
    generate_umap
)

from tools.senescence import (
    find_senescence_markers,
    senescence_score
)

from tools.age_analysis import (
    compare_across_age
)

from tools.differential_expression import (
    differential_expression
)

SPECIES = "mouse"

print("\n" + "=" * 50)
print("Loading dataset...")
print("=" * 50 + "\n")

adata = load_kidney_dataset()

print(f"Dataset shape: {adata.shape}")

# =========================
# Pipeline
# =========================

adata, species = quality_control(
    adata,
    species=SPECIES
)

adata = normalize(adata)

adata = cluster_cells(adata)

# =========================
# UMAP
# =========================

umap_path = generate_umap(adata)

print(f"UMAP saved: {umap_path}")

# =========================
# Senescence markers
# =========================

markers = find_senescence_markers(
    adata,
    species=species
)

print(markers)

# =========================
# Senescence score
# =========================

score = senescence_score(
    adata,
    species=species
)

print(score)

# =========================
# Age comparison
# =========================

age_info = compare_across_age(adata)

print(age_info)

# =========================
# Differential expression
# =========================

de = differential_expression(adata)

print(de)

print("\nPipeline complete.")