"""Functional test for marker-based cluster annotation.

Builds a synthetic dataset with two transcriptionally distinct populations
(T cells vs B cells, defined by their canonical markers) and verifies that the
deterministic annotator recovers the right cell types for the Leiden clusters,
writes a per-cell predicted column, and that generate_umap / get_cluster_annotations
pick it up when the dataset has no cell_ontology_class.

Run:  backend/venv/Scripts/python.exe -m tests.test_cell_type_annotation
"""

import os
import sys

import numpy as np
import anndata as ad
import scanpy as sc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.cell_type_annotation import (  # noqa: E402
    annotate_clusters_by_markers,
    ensure_predicted_cell_types,
    PREDICTED_COL,
)
from tools.senescence import get_cluster_annotations  # noqa: E402
from tools.visualization import generate_umap  # noqa: E402


def _synthetic_adata(seed: int = 0):
    """Two populations: T cells (CD3D/CD3E/CD2/TRAC/CD28 high) and B cells
    (CD79A/CD79B/MS4A1/CD19/IGHM high), plus background genes."""
    rng = np.random.default_rng(seed)
    n_each = 150

    t_markers = ["CD3D", "CD3E", "CD3G", "CD2", "TRAC", "CD28"]
    b_markers = ["CD79A", "CD79B", "MS4A1", "CD19", "IGHM", "EBF1"]
    background = [f"GENE{i}" for i in range(40)]
    genes = t_markers + b_markers + background
    gi = {g: i for i, g in enumerate(genes)}

    n = 2 * n_each
    X = rng.poisson(0.3, size=(n, len(genes))).astype(float)

    # T-cell block (first n_each) expresses T markers; B-cell block expresses B markers.
    for g in t_markers:
        X[:n_each, gi[g]] += rng.poisson(8, size=n_each)
    for g in b_markers:
        X[n_each:, gi[g]] += rng.poisson(8, size=n_each)

    adata = ad.AnnData(X=X)
    adata.var_names = genes
    adata.obs_names = [f"cell{i}" for i in range(n)]
    adata.obs["true_type"] = ["T cell"] * n_each + ["B cell"] * n_each
    adata.layers["counts"] = X.copy()

    # Minimal preprocessing so rank_genes_groups + leiden work.
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.pca(adata, n_comps=10)
    sc.pp.neighbors(adata)
    sc.tl.leiden(adata, flavor="igraph", n_iterations=2, directed=False)
    return adata


def test_marker_annotation_recovers_types():
    adata = _synthetic_adata()
    result = annotate_clusters_by_markers(adata, species="human")

    assert not result.get("error"), result
    assert result["predicted"] is True
    assert PREDICTED_COL in adata.obs.columns

    # Every cell's predicted type should match its ground-truth population.
    correct = (adata.obs[PREDICTED_COL].astype(str) == adata.obs["true_type"]).mean()
    print(f"per-cell agreement with ground truth: {correct:.1%}")
    assert correct > 0.95, f"expected >95% agreement, got {correct:.1%}"

    labels = set(result["cluster_annotations"].values())
    assert "T cell" in labels and "B cell" in labels, labels
    print("cluster_annotations:", result["cluster_annotations"])
    print("cluster_markers:", result["cluster_markers"])


def test_get_cluster_annotations_predicts_without_labels():
    adata = _synthetic_adata()
    out = get_cluster_annotations(adata, species="human")
    assert out.get("predicted") is True, out
    assert out.get("method") == "marker_based"
    assert set(out["cluster_annotations"].values()) >= {"T cell", "B cell"}
    print("get_cluster_annotations OK:", out["cluster_annotations"])


def test_generate_umap_colors_by_predicted():
    adata = _synthetic_adata()
    ok = ensure_predicted_cell_types(adata, species="human")
    assert ok and PREDICTED_COL in adata.obs.columns
    path = generate_umap(adata, filename="test_umap_predicted.png", species="human")
    assert os.path.exists(path), path
    print("UMAP written to:", path)


if __name__ == "__main__":
    test_marker_annotation_recovers_types()
    test_get_cluster_annotations_predicts_without_labels()
    test_generate_umap_colors_by_predicted()
    print("\nALL TESTS PASSED")
