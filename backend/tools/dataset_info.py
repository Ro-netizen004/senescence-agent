"""Lightweight dataset summary for agent context and /dataset/info API."""

def _json_value(value):
    if value is None:
        return None
    try:
        if value != value:  # NaN / NaT
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_dataset_preview(adata, row_limit: int = 20, gene_limit: int = 50) -> dict:
    """Return a bounded metadata preview; never serialize the expression matrix."""
    row_limit = max(1, min(int(row_limit), 100))
    gene_limit = max(1, min(int(gene_limit), 200))
    obs = adata.obs.iloc[:row_limit]
    rows = []
    for index, record in obs.iterrows():
        row = {"cell_id": str(index)}
        row.update({str(column): _json_value(value) for column, value in record.items()})
        rows.append(row)
    return {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "columns": ["cell_id"] + [str(c) for c in obs.columns],
        "rows": rows,
        "genes": [str(g) for g in adata.var_names[:gene_limit]],
        "row_limit": row_limit,
        "gene_limit": gene_limit,
    }


def build_dataset_summary(adata, species: str = "mouse") -> dict:
    n_cells, n_genes = adata.shape
    obs_cols = list(adata.obs.columns)

    summary = {
        "n_cells": int(n_cells),
        "n_genes": int(n_genes),
        "species": species,
        "obs_columns": obs_cols,
    }

    # Include profile-resolved column values using actual column names
    profile = adata.uns.get("dataset_profile") or {}
    summary["dataset_profile"] = profile

    age_col = profile.get("age_column") or "age"
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    sample_col = profile.get("sample_column")

    for col in (age_col, ct_col):
        if col and col in adata.obs.columns:
            values = sorted(adata.obs[col].astype(str).unique().tolist())[:30]
            summary[col] = values
            if len(adata.obs[col].unique()) > 30:
                summary[f"{col}_note"] = "truncated to 30 values"

    if sample_col and sample_col in adata.obs.columns:
        summary[sample_col] = sorted(
            adata.obs[sample_col].astype(str).unique().tolist()
        )[:30]

    # Gene-panel loading may perform ortholog resolution. Keep it out of
    # module import so lightweight preview endpoints remain local and fast.
    from tools.gene_utils import SENESCENCE_GENES, SENESCENCE_GENES_MOUSE
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
    if "qc_provenance" in adata.uns:
        summary["qc_provenance"] = adata.uns["qc_provenance"]

    return summary


def format_dataset_context(summary: dict) -> str:
    profile = summary.get("dataset_profile") or {}
    age_col = profile.get("age_column") or "age"
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    sample_col = profile.get("sample_column")
    youngest = profile.get("youngest")
    oldest = profile.get("oldest")
    age_format = profile.get("age_format")

    lines = [
        "CURRENT DATASET (do not invent values beyond tools):",
        f"- Cells: {summary.get('n_cells')}, Genes: {summary.get('n_genes')}, Species: {summary.get('species')}",
        f"- SenMayo coverage: {summary.get('senmayo_genes_found')}/{summary.get('senmayo_genes_total')} genes ({summary.get('senmayo_coverage_pct')}%)",
    ]

    # Age info — use profile-resolved column
    age_values = summary.get(age_col)
    if age_values:
        lines.append(
            f"- Age column: '{age_col}' (format: {age_format}) | "
            f"Groups: {', '.join(map(str, age_values))} | "
            f"Youngest: {youngest} | Oldest: {oldest}"
        )
        lines.append(
            f"  → Use reference_age='{youngest}' and comparison_age='{oldest}' "
            f"for young-vs-old contrasts unless user specifies otherwise."
        )
    else:
        lines.append("- Age column: not detected (age comparison / DESeq2 by age will fail)")

    # Cell type info
    ct_values = summary.get(ct_col)
    if ct_values:
        preview = ", ".join(ct_values[:8])
        if len(ct_values) > 8:
            preview += f", … ({len(ct_values)} types total)"
        lines.append(f"- Cell type column: '{ct_col}' | Types: {preview}")
    else:
        lines.append(f"- Cell type column: not detected")

    # Sample info
    if sample_col and summary.get(sample_col):
        lines.append(
            f"- Sample column: '{sample_col}' | "
            f"{len(summary[sample_col])} unique samples"
        )
    else:
        lines.append("- Sample column: not detected (statistical testing will fail)")

    # Grouping variables available for differential-expression contrasts.
    group_columns = profile.get("group_columns") or []
    if group_columns:
        parts = []
        for gc in group_columns[:6]:
            vals = ", ".join(map(str, (gc.get("values") or [])[:8]))
            parts.append(f"{gc.get('column')} [{vals}]")
        lines.append("- Grouping variables (for DESeq2 contrasts): " + " | ".join(parts))
        lines.append(
            "  → For differential expression, pass group_column + reference_group + "
            "comparison_group using values shown above."
        )

    meta = summary.get("metadata_status")
    if isinstance(meta, dict):
        lines.append(f"- Metadata check: {meta.get('status', 'unknown')}")

    return "\n".join(lines)
