import scanpy as sc
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Senescence marker genes — human names
SENESCENCE_GENES = [
    'CDKN1A', 'CDKN2A', 'IL6', 'IL8', 'LMNB1',
    'TP53', 'MKI67', 'SERPINE1', 'GLB1', 'HMGA1'
]

def normalize_gene_names(genes: list, species: str = 'mouse') -> list:
    """Convert human gene names to mouse orthologs if needed"""
    if species == 'mouse':
        return [g[0].upper() + g[1:].lower() for g in genes]
    return genes

def quality_control(adata, species: str = 'mouse'):
    """Filter low quality cells and genes"""
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)
    print(f"After QC: {adata.shape[0]} cells, {adata.shape[1]} genes")
    return adata

def normalize(adata):
    """Normalize and log transform the data"""
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    return adata

def cluster_cells(adata):
    """Cluster cells using Leiden algorithm"""
    sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)
    sc.tl.leiden(adata, flavor="igraph", n_iterations=2)
    return adata

def generate_umap(adata, filename="umap.png"):
    """Generate and save UMAP plot"""
    sc.tl.umap(adata)
    sc.pl.umap(adata, color='leiden', show=False)
    filepath = os.path.join(OUTPUT_DIR, filename)
    plt.savefig(filepath)
    plt.close()
    return filepath

def find_senescence_markers(adata, species: str = 'mouse'):
    """Check expression of known senescence marker genes"""
    genes = normalize_gene_names(SENESCENCE_GENES, species)
    found = [g for g in genes if g in adata.var_names]
    missing = [g for g in genes if g not in adata.var_names]
    return {
        "found_markers": found,
        "missing_markers": missing,
        "species": species
    }

def compare_across_age(adata, age_column: str = 'age', cell_type_column: str = 'cell_ontology_class'):
    """Show cell type composition across age groups"""
    if age_column not in adata.obs.columns:
        return {"error": f"Column '{age_column}' not found"}
    ages = adata.obs[age_column].unique().tolist()
    cell_types = adata.obs[cell_type_column].unique().tolist() if cell_type_column in adata.obs.columns else []
    return {
        "age_groups": sorted(ages),
        "cell_types": cell_types,
        "total_cells": adata.shape[0]
    }

if __name__ == "__main__":
    # Load the kidney dataset
    adata = sc.read_h5ad("data/tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad")
    print(f"Shape: {adata.shape}")
    print(f"Metadata columns: {adata.obs.columns.tolist()}")
    print(f"Ages: {adata.obs['age'].unique()}")
    print(f"Cell types: {adata.obs['cell_ontology_class'].unique()}")

    # Run pipeline
    adata = quality_control(adata, species='mouse')
    adata = normalize(adata)

    # Check senescence markers with mouse gene names
    result = find_senescence_markers(adata, species='mouse')
    print("Senescence markers found:", result["found_markers"])
    print("Senescence markers missing:", result["missing_markers"])

    # Check age groups
    age_info = compare_across_age(adata)
    print("Age groups:", age_info["age_groups"])
    print("Cell types:", age_info["cell_types"])