"""Marker-based cluster cell-type annotation (deterministic).

Assigns a biological identity to each Leiden cluster by ranking the cluster's
marker genes (Scanpy ``rank_genes_groups``) and matching them against a curated
marker -> cell-type panel. This is the *de novo* annotation path used when a
dataset ships no ``cell_ontology_class`` column and would otherwise render as
"cluster 0, cluster 1, ...".

Design notes:
- **Deterministic, inspectable.** No ML model, no network call. Every label is
  explained by the marker genes that earned it (returned in ``cluster_markers``).
- **Descriptive only.** A marker-derived label is a hypothesis about a cluster's
  identity, never a validated statistical claim. Callers must surface it as
  "predicted", with confidence, and must not feed it into inferential contrasts.
- **Species-agnostic matching.** Markers are stored as human (UPPER) symbols and
  matched case-insensitively, so mouse datasets (Title-case symbols, e.g. Cd3d)
  work with the same panel and no separate mouse dictionary.
"""

import scanpy as sc

PREDICTED_COL = "predicted_cell_type"

# Curated canonical markers per cell type. Human symbols; matched
# case-insensitively so mouse (Title-case) symbols resolve to the same entry.
# Panel intentionally covers the immune / stromal / epithelial types found in
# the aging tissues this project analyses (kidney, liver, spleen, aorta, muscle)
# plus common blood/vascular lineages.
MARKER_SETS: dict[str, list[str]] = {
    "T cell": ["CD3D", "CD3E", "CD3G", "CD2", "TRAC", "CD28"],
    "CD4+ T cell": ["CD4", "IL7R", "CCR7", "CD3D"],
    "CD8+ T cell": ["CD8A", "CD8B", "GZMK", "CD3D"],
    "NK cell": ["NKG7", "GNLY", "KLRD1", "NCAM1", "KLRB1", "GZMB"],
    "B cell": ["CD79A", "CD79B", "MS4A1", "CD19", "IGHM", "EBF1"],
    "Plasma cell": ["MZB1", "JCHAIN", "XBP1", "SDC1", "PRDM1"],
    "Macrophage": ["CD68", "LYZ", "CSF1R", "ADGRE1", "MRC1", "C1QA", "C1QB", "ITGAM"],
    "Monocyte": ["CD14", "FCGR3A", "LYZ", "S100A8", "VCAN"],
    "Dendritic cell": ["FLT3", "CLEC9A", "ITGAX", "CD83", "IRF8"],
    "Neutrophil": ["S100A8", "S100A9", "LCN2", "LTF", "MPO", "RETNLG"],
    "Mast cell": ["CPA3", "TPSAB1", "KIT", "MS4A2"],
    "Endothelial cell": ["PECAM1", "CDH5", "VWF", "CLDN5", "KDR", "FLT1", "EMCN"],
    "Fibroblast": ["COL1A1", "COL1A2", "COL3A1", "DCN", "LUM", "PDGFRA"],
    "Smooth muscle cell": ["ACTA2", "MYH11", "TAGLN", "CNN1", "MYL9"],
    "Pericyte": ["RGS5", "PDGFRB", "KCNJ8", "NOTCH3"],
    "Mesenchymal stem cell": ["PDGFRA", "THY1", "ENG", "LY6A", "NT5E"],
    "Skeletal muscle satellite cell": ["PAX7", "MYF5", "MYOD1", "DES"],
    "Skeletal muscle cell": ["ACTA1", "MYH1", "TNNT3", "CKM", "TTN"],
    "Hepatocyte": ["ALB", "APOA1", "TTR", "TF", "SERPINA1", "CYP2E1"],
    "Epithelial cell": ["EPCAM", "KRT8", "KRT18", "KRT19", "CDH1"],
    "Proximal tubule cell": ["LRP2", "SLC34A1", "SLC5A2", "MIOX", "GATM"],
    "Collecting duct cell": ["AQP2", "AQP3", "CALB1"],
    "Adipocyte": ["ADIPOQ", "LEP", "FABP4", "PLIN1"],
    "Erythrocyte": ["HBB", "HBA1", "ALAS2", "GYPA"],
}

UNKNOWN_LABEL = "unknown"


def annotate_clusters_by_markers(
    adata,
    species: str = "mouse",
    top_n: int = 50,
    min_markers: int = 2,
) -> dict:
    """Assign a predicted cell type to every Leiden cluster from its marker genes.

    Writes a per-cell ``predicted_cell_type`` column to ``adata.obs`` and returns
    a descriptive summary. Idempotent-friendly: cheap to call once per dataset
    (the expensive ``rank_genes_groups`` is cached in ``adata.uns``).

    Returns a dict with ``cluster_annotations`` (cluster -> label),
    ``cluster_confidence``, ``cluster_markers`` (the supporting genes per
    cluster), ``method``, and ``predicted=True``.
    """
    if "leiden" not in adata.obs.columns:
        return {"error": "No leiden clustering found. Run pipeline first."}

    n_clusters = adata.obs["leiden"].astype(str).nunique()
    if n_clusters < 2:
        # rank_genes_groups needs >= 2 groups; a single cluster has no contrast.
        return {"error": "Only one cluster present — nothing to differentiate."}

    # Case-insensitive lookup from marker symbol -> actual var name in this dataset.
    var_upper = {str(v).upper(): str(v) for v in adata.var_names}
    detectable = {
        ct: [m for m in markers if m in var_upper] for ct, markers in MARKER_SETS.items()
    }

    # Rank marker genes per cluster (cached — this is the only expensive step).
    if not adata.uns.get("_rgg_leiden_done"):
        sc.tl.rank_genes_groups(
            adata, "leiden", method="wilcoxon", n_genes=top_n, use_raw=False
        )
        adata.uns["_rgg_leiden_done"] = True

    ranked = adata.uns["rank_genes_groups"]["names"]
    cluster_ids = list(ranked.dtype.names)

    assignments: dict[str, dict] = {}
    for cid in cluster_ids:
        top_genes = [str(g).upper() for g in list(ranked[cid])[:top_n]]
        rank_of = {g: i for i, g in enumerate(top_genes)}
        top_set = set(top_genes)

        best_ct, best_score, best_matches = UNKNOWN_LABEL, 0.0, []
        for ct, markers in detectable.items():
            if not markers:
                continue
            matches = [m for m in markers if m in top_set]
            if len(matches) < min_markers:
                continue
            # Fraction of *detectable* markers that surface in the cluster's top
            # genes (fair across panels of different sizes), tie-broken by how
            # highly ranked those matched markers are.
            frac = len(matches) / len(markers)
            rank_weight = sum(1.0 / (rank_of[m] + 1) for m in matches)
            score = frac + 1e-3 * rank_weight
            if score > best_score:
                best_ct, best_score, best_matches = ct, score, matches

        assignments[str(cid)] = {
            "cell_type": best_ct,
            "confidence": round(min(best_score, 1.0), 3),
            "markers": [var_upper[m] for m in best_matches][:8],
        }

    mapping = {cid: a["cell_type"] for cid, a in assignments.items()}

    # Per-cell predicted label so downstream plots/tools can colour by it.
    adata.obs[PREDICTED_COL] = (
        adata.obs["leiden"].astype(str).map(mapping).fillna(UNKNOWN_LABEL).astype("category")
    )
    adata.uns["cluster_annotation_method"] = "marker_based"

    return {
        "cluster_annotations": mapping,
        "cluster_confidence": {cid: a["confidence"] for cid, a in assignments.items()},
        "cluster_markers": {cid: a["markers"] for cid, a in assignments.items()},
        "method": "marker_based",
        "predicted": True,
        "species": species,
        "total_clusters": len(mapping),
        "n_unknown": sum(1 for v in mapping.values() if v == UNKNOWN_LABEL),
    }


def ensure_predicted_cell_types(adata, species: str = "mouse") -> bool:
    """Compute marker-based predictions once, only when the dataset lacks real
    annotations. Returns True if a predicted column is available afterwards.

    No-op (returns False) when the dataset already carries ``cell_ontology_class``
    — real labels always win over predictions.
    """
    if "cell_ontology_class" in adata.obs.columns:
        return False
    if PREDICTED_COL in adata.obs.columns:
        return True
    result = annotate_clusters_by_markers(adata, species)
    return not result.get("error")
