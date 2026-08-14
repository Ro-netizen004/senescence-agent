"""Pseudobulk negative-binomial GLM differential expression (edgeR family).

A SECOND replicate-aware DE method alongside pseudobulk DESeq2, used to show that
the validity governance is a property of the statistical *unit/design*, not of one
DE implementation. It runs through the IDENTICAL pseudobulk builder and Gate 1;
only the DE computation differs.

Method: negative-binomial GLM with a **mean-trended per-gene dispersion** and a
**likelihood-ratio test** for the group coefficient (edgeR-style trended-dispersion
+ LRT). No DESeq2-style log-fold-change shrinkage.

This is an edgeR-*family* method implemented in Python (statsmodels); it is NOT
edgeR itself (edgeR is R-only). Real edgeR additionally uses empirical-Bayes
tagwise dispersions and a quasi-likelihood F-test.

Interface mirrors ``run_deseq2.run_deseq2_pseudobulk`` (same pseudobulk count_df +
meta_df in, same results columns out) so it is drop-in for the same Gate 1 and the
same null harness.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
    p = np.asarray(pvals, dtype=float)
    p[np.isnan(p)] = 1.0
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    adj = np.minimum.accumulate((ranked * n / (np.arange(n) + 1))[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(adj, 0.0, 1.0)
    return out


def _trended_dispersion(counts: np.ndarray, libsize: np.ndarray, groups: np.ndarray,
                        n_bins: int = 30) -> np.ndarray:
    """Mean-trended per-gene NB2 dispersion (edgeR trended style).

    Estimates a raw within-group method-of-moments dispersion per gene, then
    replaces it with a smooth median trend as a function of log mean expression.
    The trend is far more stable than one common value (it gives high-variance,
    low-count genes a larger dispersion) and needs no per-gene shrinkage.
    """
    norm = counts / libsize[:, None] * np.median(libsize)
    per_gene_mu = np.clip(norm.mean(axis=0), 1e-8, None)

    # Within-group pooled variance removes the (null) group-mean difference.
    ss = np.zeros(norm.shape[1])
    dof = 0
    for g in np.unique(groups):
        yg = norm[groups == g]
        if yg.shape[0] < 2:
            continue
        ss += ((yg - yg.mean(axis=0)) ** 2).sum(axis=0)
        dof += yg.shape[0] - 1
    within_var = ss / max(dof, 1)

    with np.errstate(divide="ignore", invalid="ignore"):
        raw = (within_var - per_gene_mu) / (per_gene_mu ** 2)
    raw = np.clip(np.nan_to_num(raw, nan=0.1), 1e-4, 100.0)

    logmu = np.log(per_gene_mu)
    edges = np.quantile(logmu, np.linspace(0, 1, n_bins + 1))
    edges[-1] += 1e-9
    idx = np.clip(np.digitize(logmu, edges) - 1, 0, n_bins - 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    bin_disp = np.array([
        np.median(raw[idx == b]) if np.any(idx == b) else np.nan for b in range(n_bins)
    ])
    good = ~np.isnan(bin_disp)
    if not good.any():
        return np.full(counts.shape[1], 0.1)
    trend_centers = np.interp(centers, centers[good], bin_disp[good])
    trend = np.interp(logmu, centers, trend_centers)
    return np.clip(trend, 1e-4, 100.0)


def run_nbglm_pseudobulk(
    count_df: pd.DataFrame,
    meta_df: pd.DataFrame,
    group_column: str = "group",
    reference_group=None,
    comparison_group=None,
    min_total_count: int = 10,
):
    """Trended-dispersion NB-GLM DE between two groups on pseudobulk counts, tested
    by a likelihood-ratio test. Returns the same dict shape as
    ``run_deseq2_pseudobulk`` (positive log2FC = higher in the comparison group).
    """
    import statsmodels.api as sm
    from scipy.stats import chi2

    meta = meta_df.copy()
    if group_column not in meta.columns:
        raise ValueError(
            f"Grouping column '{group_column}' not in metadata (have: {list(meta.columns)})."
        )
    meta["_group"] = meta[group_column].astype(str)
    available = meta["_group"].dropna().unique().tolist()

    if reference_group and comparison_group:
        ref_label, comp_label = str(reference_group), str(comparison_group)
        missing = [g for g in (ref_label, comp_label) if g not in available]
        if missing:
            raise ValueError(f"Requested group(s) not in '{group_column}': {missing}. "
                             f"Available: {available}.")
    elif len(available) == 2:
        ref_label, comp_label = str(available[0]), str(available[1])
    else:
        raise ValueError("Two groups required; specify reference_group and comparison_group.")

    keep_samples = meta[meta["_group"].isin([ref_label, comp_label])].index
    c = count_df.loc[keep_samples]
    meta = meta.loc[keep_samples]

    gene_totals = c.sum(axis=0)
    c = c.loc[:, gene_totals >= min_total_count]
    genes = list(c.columns)

    Y = c.values.astype(float)                                    # (n_samples, n_genes)
    groups = (meta["_group"].values == comp_label).astype(float)  # 0=ref, 1=comp
    libsize = Y.sum(axis=1)
    libsize[libsize == 0] = 1.0
    offset = np.log(libsize)
    X_full = np.column_stack([np.ones(len(groups)), groups])      # intercept + group
    X_null = np.ones((len(groups), 1))                            # intercept only

    disp = _trended_dispersion(Y, libsize, groups)

    n_genes = len(genes)
    log2fc = np.full(n_genes, np.nan)
    lfcse = np.full(n_genes, np.nan)
    stat = np.full(n_genes, np.nan)
    pvals = np.full(n_genes, np.nan)
    base = Y.mean(axis=0)
    ln2 = np.log(2.0)

    for j in range(n_genes):
        yj = Y[:, j]
        family = sm.families.NegativeBinomial(alpha=max(float(disp[j]), 1e-6))
        try:
            full = sm.GLM(yj, X_full, family=family, offset=offset).fit()
            null = sm.GLM(yj, X_null, family=family, offset=offset).fit()
            lr = 2.0 * (full.llf - null.llf)
            log2fc[j] = full.params[1] / ln2
            lfcse[j] = full.bse[1] / ln2
            stat[j] = max(lr, 0.0)
            pvals[j] = float(chi2.sf(max(lr, 0.0), 1))
        except Exception:
            pvals[j] = 1.0

    padj = _bh_fdr(pvals)
    results = pd.DataFrame(
        {"baseMean": base, "log2FoldChange": log2fc, "lfcSE": lfcse,
         "stat": stat, "pvalue": pvals, "padj": padj},
        index=pd.Index(genes, name="index"),
    ).sort_values("padj")

    return {
        "results": results,
        "method": "nbglm_trended_lrt",
        "dispersion_model": "mean_trended",
        "test": "likelihood_ratio",
        "median_dispersion": round(float(np.median(disp)), 5),
        "group_column": group_column,
        "reference_group": ref_label,
        "comparison_group": comp_label,
        "youngest_group": ref_label,   # legacy aliases for shared callers
        "oldest_group": comp_label,
    }
