"""
UNGOVERNED (per-cell) inference tools — for the governance ablation ONLY.

These deliberately commit pseudoreplication: they treat individual cells as
independent observations across biological groups. They exist so we can run a
real end-to-end *ungoverned* agent (per-cell tests + no gates + LLM narration)
and contrast it with the governed agent on identical prompts/data.

DO NOT wire these into the production tool map. They are activated only when
AGENT_GOVERNANCE=off (see agent.governance).
"""

from __future__ import annotations

import numpy as np
from scipy.stats import mannwhitneyu

from tools.age_analysis import _resolve_cell_type
from tools.senescence import senescence_score as _senescence_score


def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values."""
    p = np.asarray(pvals, dtype=float)
    p[np.isnan(p)] = 1.0
    n = len(p)
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order]
    adj = ranked * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(adj, 0, 1)
    return out


def _dense(x):
    return x.toarray() if hasattr(x, "toarray") else np.asarray(x)


def _resolve(adata, cell_type, cell_type_column):
    available = sorted(adata.obs[cell_type_column].astype(str).unique().tolist())
    return _resolve_cell_type(cell_type, available), available


def differential_expression_percell(
    adata,
    cell_type: str,
    age_column: str = "age",
    cell_type_column: str = "cell_ontology_class",
    sample_column: str = "sample_id",
    reference_age: str = "3m",
    comparison_age: str = "24m",
    species: str = "mouse",
    min_detection_frac: float = 0.10,
):
    """Per-cell Wilcoxon differential expression between two ages (PSEUDOREPLICATION)."""
    if cell_type_column not in adata.obs.columns:
        return {"error": f"Column '{cell_type_column}' not found."}
    if age_column not in adata.obs.columns:
        return {"error": f"Column '{age_column}' not found."}

    resolved, available = _resolve(adata, cell_type, cell_type_column)
    if not resolved:
        return {"error": f"Cell type '{cell_type}' not found. Available: {available}"}

    ref, comp = str(reference_age), str(comparison_age)
    sub = adata[adata.obs[cell_type_column].astype(str) == resolved]
    mask_ref = sub.obs[age_column].astype(str) == ref
    mask_comp = sub.obs[age_column].astype(str) == comp
    n_ref, n_comp = int(mask_ref.sum()), int(mask_comp.sum())
    if n_ref < 2 or n_comp < 2:
        return {
            "error": f"Too few cells for {resolved} at {ref}/{comp} (n={n_ref}/{n_comp}).",
        }

    X = _dense(sub.X)
    Xr, Xc = X[mask_ref.values], X[mask_comp.values]

    detect = (X > 0).mean(axis=0)
    keep = np.asarray(detect >= min_detection_frac).ravel()
    genes = np.asarray(sub.var_names)[keep]
    Xr, Xc = Xr[:, keep], Xc[:, keep]
    n_genes = int(keep.sum())

    pvals = np.asarray(
        mannwhitneyu(Xr, Xc, axis=0, alternative="two-sided").pvalue, dtype=float
    )
    pvals[np.isnan(pvals)] = 1.0  # constant genes -> not significant
    padj = _bh_fdr(pvals)

    log2fc = Xc.mean(axis=0) - Xr.mean(axis=0)  # log-normalized difference
    log2fc = np.asarray(log2fc).ravel()

    order = np.argsort(padj)
    rows = []
    for i in order[:100]:
        rows.append({
            "gene": str(genes[i]),
            "log2FoldChange": round(float(log2fc[i]), 4),
            "pvalue": float(pvals[i]),
            "padj": float(padj[i]),
        })

    n_sig = int((padj < 0.05).sum())
    return {
        "status": "ok",
        "method": "per_cell_wilcoxon",
        "cell_type": resolved,
        "reference_age": ref,
        "comparison_age": comp,
        "youngest_group": ref,
        "oldest_group": comp,
        "n_cells": {"reference": n_ref, "comparison": n_comp},
        "n_genes_tested": n_genes,
        "n_significant_fdr_0_05": n_sig,
        "results": rows,
        "statistical_unit": "cell",
    }


def test_senescence_difference_percell(
    adata,
    cell_type: str,
    age_column: str = "age",
    cell_type_column: str = "cell_ontology_class",
    sample_column: str = "sample_id",
    reference_age: str = "3m",
    comparison_age: str = "24m",
    species: str = "mouse",
):
    """Mann-Whitney on per-CELL SenMayo scores between two ages (PSEUDOREPLICATION)."""
    if not cell_type:
        return {"error": "cell_type is required."}
    if cell_type_column not in adata.obs.columns:
        return {"error": f"Column '{cell_type_column}' not found."}

    resolved, available = _resolve(adata, cell_type, cell_type_column)
    if not resolved:
        return {"error": f"Cell type '{cell_type}' not found. Available: {available}"}

    if "senescence_score" not in adata.obs.columns:
        _senescence_score(adata, species)

    ref, comp = str(reference_age), str(comparison_age)
    sub = adata[adata.obs[cell_type_column].astype(str) == resolved]
    ref_scores = sub.obs.loc[sub.obs[age_column].astype(str) == ref, "senescence_score"].to_numpy()
    comp_scores = sub.obs.loc[sub.obs[age_column].astype(str) == comp, "senescence_score"].to_numpy()

    if len(ref_scores) < 2 or len(comp_scores) < 2:
        return {
            "error": f"Too few cells for {resolved} at {ref}/{comp}.",
        }

    stat, p_value = mannwhitneyu(comp_scores, ref_scores, alternative="two-sided")
    ref_med, comp_med = float(np.median(ref_scores)), float(np.median(comp_scores))

    return {
        "status": "ok",
        "test": "mannwhitneyu",
        "method": "per_cell",
        "cell_type": resolved,
        "reference_age": ref,
        "comparison_age": comp,
        "n_cells": {"reference": int(len(ref_scores)), "comparison": int(len(comp_scores))},
        "median_score_reference": round(ref_med, 4),
        "median_score_comparison": round(comp_med, 4),
        "effect_size": round(comp_med - ref_med, 4),
        "u_statistic": float(stat),
        "p_value": float(p_value),
        "significant_at_0.05": bool(p_value < 0.05),
        "statistical_unit": "cell",
    }
