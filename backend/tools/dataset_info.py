"""Lightweight dataset summary for agent context and /dataset/info API."""

from tools.gene_utils import SENESCENCE_GENES, SENESCENCE_GENES_MOUSE


def build_dataset_summary(adata, species: str = "mouse") -> dict:
    n_cells, n_genes = adata.shape
    obs_cols = list(adata.obs.columns)

    summary = {
        "n_cells": int(n_cells),
        "n_genes": int(n_genes),
        "species": species,
        "obs_columns": obs_cols,
    }

    for col in ("age", "cell_ontology_class", "sample_id", "mouse.id", "mouse_id"):
        if col in adata.obs.columns:
            values = sorted(adata.obs[col].astype(str).unique().tolist())[:30]
            summary[col] = values
            if col in ("age", "cell_ontology_class") and len(adata.obs[col].unique()) > 30:
                summary[f"{col}_note"] = "truncated to 30 values"

    genes = SENESCENCE_GENES_MOUSE if species == "mouse" else SENESCENCE_GENES
    found = [g for g in genes if g in adata.var_names]
    summary["senmayo_genes_found"] = len(found)
    summary["senmayo_genes_total"] = len(genes)
    summary["senmayo_coverage_pct"] = round(len(found) / len(genes) * 100, 1) if genes else 0

    if "leiden" in adata.obs.columns:
        summary["n_clusters"] = int(adata.obs["leiden"].nunique())

    if "pipeline_state" in adata.uns:
        summary["pipeline_state"] = adata.uns["pipeline_state"]

    if "metadata_status" in adata.uns:
        summary["metadata_status"] = adata.uns["metadata_status"]

    return summary


def format_dataset_context(summary: dict) -> str:
    lines = [
        "CURRENT DATASET (do not invent values beyond tools):",
        f"- Cells: {summary.get('n_cells')}, Genes: {summary.get('n_genes')}, Species setting: {summary.get('species')}",
        f"- SenMayo coverage: {summary.get('senmayo_genes_found')}/{summary.get('senmayo_genes_total')} genes ({summary.get('senmayo_coverage_pct')}%)",
    ]

    if summary.get("age"):
        lines.append(f"- Age groups: {', '.join(map(str, summary['age']))}")
    else:
        lines.append("- Age column: not present (age comparison / DESeq2 by age will fail)")

    if summary.get("cell_ontology_class"):
        types = summary["cell_ontology_class"]
        preview = ", ".join(types[:8])
        if len(types) > 8:
            preview += f", … ({len(types)} types total)"
        lines.append(f"- Cell types: {preview}")

    sample_col = None
    for col in ("sample_id", "mouse.id", "mouse_id"):
        if summary.get(col):
            sample_col = col
            break
    if sample_col:
        lines.append(f"- Sample IDs ({sample_col}): {len(summary[sample_col])} unique")
    else:
        lines.append("- Sample column: not detected (pseudobulk DESeq2 may fail)")

    meta = summary.get("metadata_status")
    if isinstance(meta, dict):
        lines.append(f"- Metadata check: {meta.get('status', 'unknown')}")

    return "\n".join(lines)
