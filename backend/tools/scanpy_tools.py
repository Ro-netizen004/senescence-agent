import scanpy as sc
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for saving plots
import matplotlib.pyplot as plt
import os

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def normalize_genes(genes: list, species: str) -> list:
    return [g.capitalize() if species == 'mouse' else g for g in genes]

def quality_control(adata):
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

def find_senescence_markers(adata):
    """Check expression of known senescence marker genes"""
    senescence_genes = ['CDKN1A', 'CDKN2A', 'IL6', 'IL8', 'LMNB1']
    found = [g for g in senescence_genes if g in adata.var_names]
    missing = [g for g in senescence_genes if g not in adata.var_names]
    return {
        "found_markers": found,
        "missing_markers": missing
    }

if __name__ == "__main__":
    adata = sc.datasets.pbmc3k()
    adata = quality_control(adata)
    adata = normalize(adata)
    result = find_senescence_markers(adata)
    print("Senescence markers found:", result["found_markers"])
    print("Senescence markers missing:", result["missing_markers"])