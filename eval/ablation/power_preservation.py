"""
Result #2: Power preservation.

Shows the governed pseudobulk path DETECTS a real effect when one exists, so its
~0 false discoveries on nulls (Result #1) reflect calibration, not deafness.

Data: GSE226225 (WI-38 fibroblasts). Non-senescent = CTRL + ETO day-0; senescent
= RS / IR / ETO. This is a large, known real difference with true DE genes.

We run governed pseudobulk (per-sample) DE, senescent vs non-senescent, and:
  - count DE genes at FDR<0.05 (should be large -> power preserved)
  - check recovery of canonical senescence markers (CDKN1A/p21, etc.)
  - for contrast, run ungoverned per-cell DE (also detects, but inflated)

Together with Result #1 (governed ~0 on nulls) this gives the 2x2:
governed is silent on nulls and detective on real effects.

Usage:
    python eval/ablation/power_preservation.py
"""

import os
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np
import pandas as pd
import scanpy as sc

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# .env for GSE_DATA_DIR
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

H5AD = Path(os.environ.get("GSE_DATA_DIR", str(ROOT / "data" / "gse226225"))) / "GSE226225.h5ad"

ALPHA = 0.05
# Canonical senescence markers (human symbols) expected to move with senescence.
SEN_MARKERS = ["CDKN1A", "CDKN2A", "SERPINE1", "IL6", "CXCL8", "IL1B", "GLB1",
               "MMP3", "IGFBP3", "TP53", "GDF15", "TNFRSF10C", "MKI67", "LMNB1"]


def _bh(p):
    p = np.asarray(p, float); p[np.isnan(p)] = 1.0
    n = len(p); o = np.argsort(p); r = p[o]
    adj = np.minimum.accumulate((r * n / (np.arange(n) + 1))[::-1])[::-1]
    out = np.empty(n); out[o] = np.clip(adj, 0, 1); return out


def label_group(condition: str) -> str:
    c = str(condition).upper()
    if c.startswith("CTRL") or "DAY_0" in c:
        return "non_senescent"
    if c.startswith(("RS", "IR", "ETO")):
        return "senescent"
    return "other"


def pseudobulk(adata, sample_col="sample_id"):
    """Sum raw counts per sample -> (samples x genes) integer matrix + group meta.
    Sums sparsely, one sample at a time, to avoid densifying the full matrix."""
    X = adata.X  # keep sparse
    samples = adata.obs[sample_col].astype(str).values
    groups = adata.obs["group"].astype(str).values
    rows, meta_rows = {}, {}
    for s in pd.unique(samples):
        idx = np.where(samples == s)[0]
        row_sum = np.asarray(X[idx].sum(axis=0)).ravel()  # sparse slice -> dense 1D
        rows[s] = row_sum
        meta_rows[s] = groups[idx[0]]
    counts = pd.DataFrame(rows, index=adata.var_names).T.round().astype(int)
    meta = pd.DataFrame({"group": pd.Series(meta_rows)})
    return counts, meta


def governed_deseq2(counts, meta, ref="non_senescent", alt="senescent"):
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats
    sub = meta[meta["group"].isin([ref, alt])]
    c = counts.loc[sub.index]
    # keep genes with enough total counts
    c = c.loc[:, c.sum(axis=0) >= 10]
    dds = DeseqDataSet(counts=c, metadata=sub, design_factors="group", quiet=True)
    dds.deseq2()
    st = DeseqStats(dds, contrast=["group", alt, ref], quiet=True)
    st.summary()
    res = st.results_df.dropna(subset=["padj"])
    return res


def ungoverned_percell(adata, ref="non_senescent", alt="senescent",
                       min_frac=0.10, max_cells_per_group=3000, seed=0):
    """Per-cell Wilcoxon DE. Subsamples cells per group and gene-filters on the
    sparse matrix before densifying, to bound memory."""
    from scipy.stats import mannwhitneyu
    import scanpy as _sc
    rng = np.random.default_rng(seed)

    tmp = adata[adata.obs["group"].isin([ref, alt])].copy()
    _sc.pp.normalize_total(tmp, target_sum=1e4); _sc.pp.log1p(tmp)  # sparse-safe

    g = tmp.obs["group"].astype(str).values
    idx_a = np.where(g == alt)[0]; idx_b = np.where(g == ref)[0]
    if len(idx_a) > max_cells_per_group:
        idx_a = rng.choice(idx_a, max_cells_per_group, replace=False)
    if len(idx_b) > max_cells_per_group:
        idx_b = rng.choice(idx_b, max_cells_per_group, replace=False)

    Xln = tmp.X  # sparse
    # gene filter on sparse (detection fraction over the subsampled cells)
    sel = np.concatenate([idx_a, idx_b])
    detect = np.asarray((Xln[sel] > 0).sum(axis=0)).ravel() / len(sel)
    keep = detect >= min_frac
    a = np.asarray(Xln[idx_a][:, keep].todense())
    b = np.asarray(Xln[idx_b][:, keep].todense())
    p = np.asarray(mannwhitneyu(a, b, axis=0, alternative="two-sided").pvalue, float)
    p[np.isnan(p)] = 1.0
    padj = _bh(p)
    return int((padj < ALPHA).sum()), int(keep.sum())


def main():
    if not H5AD.exists():
        print(f"ERROR: GSE226225 not found at {H5AD}. Set GSE_DATA_DIR."); sys.exit(1)

    print(f"Loading {H5AD}...")
    adata = sc.read_h5ad(str(H5AD))
    adata.obs["group"] = adata.obs["condition"].map(label_group)
    adata = adata[adata.obs["group"].isin(["senescent", "non_senescent"])].copy()
    adata.var_names_make_unique()

    n_by = adata.obs.groupby(["group", "sample_id"], observed=True).size()
    print("Samples per group:")
    print(adata.obs.groupby("group")["sample_id"].nunique())

    # ── Governed pseudobulk (the power test) ──
    print("\nBuilding pseudobulk + governed DESeq2 (senescent vs non_senescent)...")
    counts, meta = pseudobulk(adata)
    res = governed_deseq2(counts, meta)
    sig = res[res["padj"] < ALPHA]
    up = sig[sig["log2FoldChange"] > 0]
    n_sig, n_up = int(len(sig)), int(len(up))
    print(f"  Governed: {n_sig} DE genes at FDR<{ALPHA} ({n_up} up in senescent).")

    # marker recovery
    markers_found = {}
    for m in SEN_MARKERS:
        if m in res.index:
            r = res.loc[m]
            markers_found[m] = {
                "log2FC": round(float(r["log2FoldChange"]), 3),
                "padj": float(r["padj"]) if pd.notna(r["padj"]) else None,
                "significant": bool(pd.notna(r["padj"]) and r["padj"] < ALPHA),
            }
    n_markers_sig = sum(1 for v in markers_found.values() if v["significant"])
    print(f"  Senescence markers significant: {n_markers_sig}/{len(markers_found)} detected")
    for m, v in markers_found.items():
        flag = "*" if v["significant"] else " "
        print(f"    {flag} {m}: log2FC={v['log2FC']}, padj={v['padj']}")

    # ── Ungoverned per-cell (also detects, but inflated) ──
    print("\nUngoverned per-cell DE (same contrast)...")
    n_percell, n_genes = ungoverned_percell(adata)
    print(f"  Ungoverned: {n_percell} DE genes at FDR<{ALPHA} (of {n_genes} tested).")

    top = sig.reindex(sig["padj"].sort_values().index).head(20)
    results = {
        "dataset": "GSE226225",
        "contrast": "senescent vs non_senescent",
        "n_samples": {
            "senescent": int(adata.obs[adata.obs.group == "senescent"]["sample_id"].nunique()),
            "non_senescent": int(adata.obs[adata.obs.group == "non_senescent"]["sample_id"].nunique()),
        },
        "governed_pseudobulk": {
            "n_de_genes_fdr": n_sig,
            "n_up_in_senescent": n_up,
            "senescence_markers_significant": f"{n_markers_sig}/{len(markers_found)}",
            "markers": markers_found,
            "top_genes": [
                {"gene": g, "log2FC": round(float(top.loc[g, "log2FoldChange"]), 3),
                 "padj": float(top.loc[g, "padj"])}
                for g in top.index
            ],
        },
        "ungoverned_percell": {"n_de_genes_fdr": n_percell, "n_genes_tested": n_genes},
        "interpretation": (
            "Governed pseudobulk detects a large real senescence program "
            f"({n_sig} DE genes, {n_markers_sig} canonical markers) on GSE226225, "
            "versus ~0.47 mean false genes on constructed nulls (Result 1). "
            "Governance is selective: silent on nulls, detective on real effects."
        ),
    }
    (OUT_DIR / "power_preservation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved: {OUT_DIR / 'power_preservation.json'}")


if __name__ == "__main__":
    main()
