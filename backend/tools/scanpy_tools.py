import scanpy as sc
import mygene
import matplotlib

matplotlib.use('Agg')

import matplotlib.pyplot as plt
import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =========================
# Load SenMayo gene list
# =========================

def load_kidney_dataset():
    """
    Load Tabula Muris Senis Kidney dataset (.h5ad).
    """

    import os
    import scanpy as sc

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    path = os.path.join(
        BASE_DIR,
        "data",
        "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
    )

    print(f"Loading dataset from: {path}")

    adata = sc.read_h5ad(path)

    return adata

def load_senmayo_genes():
    """
    Load senescence-associated genes from SenMayo JSON file.
    """

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    path = os.path.join(
        BASE_DIR,
        "data",
        "senmayo.json"
    )

    with open(path, "r") as f:
        data = json.load(f)

    return data["SAUL_SEN_MAYO"]["geneSymbols"]


SENESCENCE_GENES = load_senmayo_genes()

# =========================
# MyGene setup
# =========================

mg = mygene.MyGeneInfo()

# Known problem genes where simple capitalization fails
# e.g. TP53 -> Trp53 (not Tp53), IL8 -> Cxcl15 (mouse proxy)
HUMAN_TO_MOUSE_FALLBACK = {
    'CDKN1A':  'Cdkn1a',
    'CDKN2A':  'Cdkn2a',
    'IL6':     'Il6',
    'IL8':     'Cxcl15',   # mouse proxy for human IL8
    'LMNB1':   'Lmnb1',
    'TP53':    'Trp53',    # critical: NOT Tp53
    'MKI67':   'Mki67',
    'SERPINE1':'Serpine1',
    'GLB1':    'Glb1',
    'HMGA1':   'Hmga1',
}

# =========================
# Gene name normalization
# =========================

def normalize_gene_names(
    genes: list,
    species: str = "mouse"
) -> list:
    """
    Convert human gene symbols to mouse orthologs.

    Uses MyGene API for accurate conversion.
    Falls back to capitalization rules if API unavailable.

    Examples:
        CDKN1A -> Cdkn1a
        TP53   -> Trp53  (not Tp53 — handled by fallback dict)
        IL6    -> Il6
    """

    if species != "mouse":
        return genes

    converted = []

    try:
        result = mg.querymany(
            genes,
            scopes="symbol",
            fields="symbol",
            species="mouse",
            returnall=True
        )

        hits = result.get("out", [])

        for i, gene in enumerate(genes):

            if i < len(hits) and "symbol" in hits[i]:
                converted.append(hits[i]["symbol"])

            else:
                # Use fallback dict first, then simple capitalization
                fallback = HUMAN_TO_MOUSE_FALLBACK.get(gene)

                if fallback:
                    converted.append(fallback)
                elif len(gene) > 1:
                    converted.append(
                        gene[0].upper() + gene[1:].lower()
                    )
                else:
                    converted.append(gene.upper())

    except Exception as e:

        print(f"MyGene lookup failed: {e}")
        print("Using fallback dictionary + capitalization method.")

        for gene in genes:
            fallback = HUMAN_TO_MOUSE_FALLBACK.get(gene)

            if fallback:
                converted.append(fallback)
            elif len(gene) > 1:
                converted.append(
                    gene[0].upper() + gene[1:].lower()
                )
            else:
                converted.append(gene.upper())

    return converted


# Run once at module load — cached for all function calls
# Avoids repeated API calls during demo
print("Converting SenMayo genes to mouse orthologs...")
SENESCENCE_GENES_MOUSE = normalize_gene_names(
    SENESCENCE_GENES,
    species="mouse"
)
print(f"Loaded {len(SENESCENCE_GENES_MOUSE)} SenMayo mouse genes.")

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

    print("Normalization complete.")

    return adata

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
        score_name="senescence_score"
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

    # Per-cluster mean scores — sorted highest first
    cluster_scores = (
        adata.obs
        .groupby("leiden")["senescence_score"]
        .mean()
        .sort_values(ascending=False)
    )

    top_cluster = cluster_scores.index[0]

    # Map cluster → most common cell type (if column exists)
    top_celltype = None
    if "cell_ontology_class" in adata.obs.columns:
        cluster_to_celltype = (
            adata.obs
            .groupby("leiden")["cell_ontology_class"]
            .agg(lambda x: x.value_counts().index[0])
        )
        top_celltype = cluster_to_celltype[top_cluster]

    print(f"Highest senescence cluster: {top_cluster} "
          f"(mean score: {cluster_scores.iloc[0]:.4f})")

    if top_celltype:
        print(f"Most common cell type in that cluster: {top_celltype}")

    return {
        "top_senescent_cluster": top_cluster,
        "top_senescent_cell_type": top_celltype,
        "genes_used": len(available),
        "total_senmayo_genes": len(genes),
        "mean_score": round(float(score_summary["mean"]), 4),
        "max_score": round(float(score_summary["max"]), 4),
        "cluster_scores": cluster_scores.round(4).to_dict(),
        "plot_path": filepath
    }

# =========================
# Age comparison
# =========================

def compare_across_age(
    adata,
    age_column: str = "age",
    cell_type_column: str = "cell_ontology_class"
):
    if age_column not in adata.obs.columns:
        return {"error": f"Column '{age_column}' not found. "
                         f"Available: {adata.obs.columns.tolist()}"}

    ages = sorted(adata.obs[age_column].astype(str).unique().tolist())

    age_counts = (
        adata.obs[age_column]
        .astype(str)
        .value_counts()
        .sort_index()
        .to_dict()
    )

    result = {
        "age_groups": ages,
        "age_counts": age_counts,
        "total_cells": adata.shape[0]
    }

    # Cell type proportions per age group
    if cell_type_column in adata.obs.columns:
        cross_tab = (
            adata.obs
            .groupby([age_column, cell_type_column], observed=True)
            .size()
            .unstack(fill_value=0)
        )
        proportions = cross_tab.div(cross_tab.sum(axis=1), axis=0)
        result["cell_type_proportions"] = proportions.round(3).to_dict()
        result["cell_types"] = sorted(
            adata.obs[cell_type_column].astype(str).unique().tolist()
        )

    # Senescence score trend across age
    # Only available if senescence_score was called first
    if "senescence_score" in adata.obs.columns:
        age_senescence = (
            adata.obs
            .groupby(age_column, observed=True)["senescence_score"]
            .mean()
            .sort_index()
            .round(4)
            .to_dict()
        )
        result["senescence_by_age"] = age_senescence

        # Find age group with highest senescence
        top_age = max(age_senescence, key=age_senescence.get)
        result["most_senescent_age"] = top_age

        print(f"Senescence by age: {age_senescence}")
        print(f"Most senescent age group: {top_age}")

    print(f"Age groups found: {ages}")

    return result

# =========================
# Main test run
# =========================

if __name__ == "__main__":

    # ── Config ────────────────────────────────────────────
    SPECIES = "mouse"

    print("\n" + "="*50)
    print("Loading Tabula Muris Senis Kidney dataset...")
    print("="*50 + "\n")

    adata = load_kidney_dataset()

    print(f"Dataset shape: {adata.shape}")
    print(f"Species: {SPECIES}")
    print(f"Metadata columns:\n{adata.obs.columns.tolist()}\n")

    if "age" in adata.obs.columns:
        print(f"Age groups: {adata.obs['age'].unique()}")

    if "cell_ontology_class" in adata.obs.columns:
        print(f"Cell types: {adata.obs['cell_ontology_class'].unique()}\n")

    # ── Pipeline ──────────────────────────────────────────
    print("\n" + "="*50)
    print("Running analysis pipeline...")
    print("="*50 + "\n")

    adata, species = quality_control(adata, species=SPECIES)
    adata = normalize(adata)
    adata = cluster_cells(adata)

    print("\nCluster counts:")
    print(adata.obs["leiden"].value_counts())

    # ── UMAP ──────────────────────────────────────────────
    print("\n" + "="*50)
    print("Generating UMAP...")
    print("="*50 + "\n")

    umap_path = generate_umap(adata)

    # ── Senescence markers ─────────────────────────────────
    print("\n" + "="*50)
    print("Checking senescence markers...")
    print("="*50 + "\n")

    markers = find_senescence_markers(adata, species=species)
    print(f"Found:    {markers['found_markers']}")
    print(f"Missing:  {markers['missing_markers']}")
    print(f"Coverage: {markers['coverage_pct']}%")

    # ── Senescence score ───────────────────────────────────
    print("\n" + "="*50)
    print("Scoring cells for senescence...")
    print("="*50 + "\n")

    score = senescence_score(adata, species=species)
    print(f"Genes used:            {score['genes_used']}/{score['total_senmayo_genes']}")
    print(f"Mean score:            {score['mean_score']}")
    print(f"Max score:             {score['max_score']}")
    print(f"Top senescent cluster: {score['top_senescent_cluster']}")
    print(f"Cluster scores:        {score['cluster_scores']}")

    # ── Age comparison ─────────────────────────────────────
    print("\n" + "="*50)
    print("Age group summary...")
    print("="*50 + "\n")

    age_info = compare_across_age(adata)
    print(f"Age groups:    {age_info['age_groups']}")
    print(f"Cells per age: {age_info['age_counts']}")
    print(f"Cell types:    {age_info['cell_types']}")

    print("\n" + "="*50)
    print("Pipeline complete. Check outputs/ for plots.")
    print("="*50 + "\n")