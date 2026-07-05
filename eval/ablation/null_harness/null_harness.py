"""
NULL HARNESS (gene-level) — the headline experiment.

Constructs a known-null condition (no real difference) by randomly assigning
whole biological replicates (mice) to two fake groups, then counts how many
FALSE-POSITIVE genes each differential-expression method reports. Because group
assignment is random over one identical population, the truth is "no DE genes";
every reported gene is a false positive. (Squair et al. 2021 null construction.)

Two methods, mirroring the agent's governed vs ungoverned paths:
  - PER-CELL Wilcoxon  (ungoverned): cells treated as independent -> pseudoreplication
  - PER-MOUSE pseudobulk t-test (governed): one profile per biological replicate

Two layers:
  Layer 1 (test):  # false-positive genes, per method, per null split
  Layer 2 (agent): ungoverned agent reports a DE finding (>=1 gene) vs governed

Usage:
    python eval/ablation/null_harness.py
    python eval/ablation/null_harness.py --cell-type "fenestrated cell" --n-perm 200

Output:
    eval/results/ablation/null_harness_results.json
    eval/results/ablation/null_harness_report.md
"""

import sys
import json
import argparse
import warnings
from pathlib import Path

import numpy as np
from scipy.stats import ttest_ind

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from agent.pipeline import ensure_pipeline
from tools.build_pseudobulk import _get_sample_column

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DATA = ROOT / "backend" / "data" / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"

ALPHA = 0.05
MIN_CELLS_PER_SAMPLE = 20      # a mouse needs >= this many cells of the type
MIN_GENE_DETECTION_FRAC = 0.10  # keep genes detected in >= 10% of the subset cells


def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values."""
    p = np.asarray(pvals, dtype=float)
    p[np.isnan(p)] = 1.0
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]
    adj = ranked * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(adj, 0, 1)
    return out


def run(data_path: Path, cell_type: str, n_perm: int, seed: int, restrict_age):
    import scanpy as sc

    if not data_path.exists():
        print(f"ERROR: dataset not found: {data_path}")
        sys.exit(1)

    print(f"Loading {data_path.name}...")
    adata = sc.read_h5ad(str(data_path))
    ensure_pipeline(adata, "mouse")

    profile = adata.uns.get("dataset_profile") or {}
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    age_col = profile.get("age_column") or "age"
    sample_col = _get_sample_column(adata, profile.get("sample_column") or "sample_id")

    if not cell_type:
        # most abundant cell type that has enough mice with enough cells
        counts = adata.obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
        mice_ge = (counts >= MIN_CELLS_PER_SAMPLE).sum(axis=1)
        cell_type = mice_ge.sort_values(ascending=False).index[0]
    print(f"Cell type: {cell_type}")
    print(f"Sample column: {sample_col}")

    sub = adata[adata.obs[ct_col].astype(str) == str(cell_type)].copy()
    if restrict_age:
        sub = sub[sub.obs[age_col].astype(str) == str(restrict_age)].copy()

    # Use log-normalized expression (never raw counts) for DE.
    sub.uns.pop("log1p", None)

    # Mice with enough cells = the biological replicates.
    vc = sub.obs[sample_col].astype(str).value_counts()
    mice = sorted(vc[vc >= MIN_CELLS_PER_SAMPLE].index.tolist())
    n_mice = len(mice)
    print(f"Usable biological replicates (mice with >={MIN_CELLS_PER_SAMPLE} cells): {n_mice}")
    print(f"  {mice}")
    if n_mice < 4:
        print("ERROR: need >= 4 mice to form two groups. Try a more abundant cell type.")
        sys.exit(1)

    # Restrict to mice-with-enough-cells and gene-filter.
    sub = sub[sub.obs[sample_col].astype(str).isin(mice)].copy()
    X = sub.X
    if hasattr(X, "toarray"):
        Xd = X.toarray()
    else:
        Xd = np.asarray(X)
    detect_frac = (Xd > 0).mean(axis=0)
    keep = detect_frac >= MIN_GENE_DETECTION_FRAC
    Xd = Xd[:, keep]
    genes = sub.var_names[keep]
    n_genes = Xd.shape[1]
    print(f"Genes retained (detected in >={MIN_GENE_DETECTION_FRAC:.0%} of cells): {n_genes}")

    cell_mouse = sub.obs[sample_col].astype(str).values

    # Precompute per-mouse mean expression (pseudobulk profiles) once.
    mouse_means = np.vstack([Xd[cell_mouse == m].mean(axis=0) for m in mice])  # (n_mice, n_genes)

    half = n_mice // 2
    rng = np.random.default_rng(seed)

    fp_percell, fp_percell_fdr = [], []
    fp_pseudobulk, fp_pseudobulk_fdr = [], []
    ungoverned_claims = 0   # ungoverned agent reports >=1 DE gene (FDR)
    governed_claims = 0     # governed agent reports >=1 DE gene (FDR)
    n_valid = 0

    print(f"\nRunning {n_perm} null permutations (random mouse-to-group assignment)...")
    for it in range(n_perm):
        perm = rng.permutation(n_mice)
        idx_a, idx_b = perm[:half], perm[half:2 * half]
        mice_a = set(np.array(mice)[idx_a])
        mice_b = set(np.array(mice)[idx_b])

        mask_a = np.isin(cell_mouse, list(mice_a))
        mask_b = np.isin(cell_mouse, list(mice_b))
        if mask_a.sum() < 2 or mask_b.sum() < 2:
            continue

        # ── PER-CELL Wilcoxon (ungoverned, pseudoreplication) ──
        # Vectorized rank-sum across all genes at once (scipy axis=0).
        from scipy.stats import mannwhitneyu
        ca, cb = Xd[mask_a], Xd[mask_b]
        p_cell = np.asarray(
            mannwhitneyu(ca, cb, axis=0, alternative="two-sided").pvalue, dtype=float
        )
        p_cell[np.isnan(p_cell)] = 1.0  # constant genes -> not significant
        padj_cell = _bh_fdr(p_cell)

        # ── PER-MOUSE pseudobulk t-test (governed) ──
        pa = mouse_means[idx_a]   # (half, n_genes)
        pb = mouse_means[idx_b]
        t, p_pb = ttest_ind(pa, pb, axis=0, equal_var=False)
        p_pb = np.where(np.isnan(p_pb), 1.0, p_pb)
        padj_pb = _bh_fdr(p_pb)

        n_valid += 1
        fpc = int((p_cell < ALPHA).sum());     fp_percell.append(fpc)
        fpcf = int((padj_cell < ALPHA).sum());  fp_percell_fdr.append(fpcf)
        fpp = int((p_pb < ALPHA).sum());        fp_pseudobulk.append(fpp)
        fppf = int((padj_pb < ALPHA).sum());    fp_pseudobulk_fdr.append(fppf)

        if fpcf > 0:
            ungoverned_claims += 1
        if fppf > 0:
            governed_claims += 1

        if (it + 1) % 25 == 0:
            print(f"  {it+1}/{n_perm} | per-cell FP(FDR)~{np.mean(fp_percell_fdr):.0f} "
                  f"pseudobulk FP(FDR)~{np.mean(fp_pseudobulk_fdr):.1f}")

    def _stats(x):
        arr = np.array(x) if x else np.array([0])
        return {"mean": round(float(arr.mean()), 2), "median": float(np.median(arr)),
                "max": int(arr.max())}

    results = {
        "dataset": data_path.name,
        "cell_type": str(cell_type),
        "restrict_age": restrict_age,
        "n_biological_replicates": n_mice,
        "group_size": half,
        "n_genes_tested": n_genes,
        "n_permutations_valid": n_valid,
        "alpha": ALPHA,
        "truth": "null (random mouse-to-group split of one population); expected DE genes = 0",
        "layer1_false_positive_genes": {
            "per_cell_raw_p": _stats(fp_percell),
            "per_cell_fdr": _stats(fp_percell_fdr),
            "pseudobulk_raw_p": _stats(fp_pseudobulk),
            "pseudobulk_fdr": _stats(fp_pseudobulk_fdr),
        },
        "layer2_agent_claim_rate": {
            "ungoverned_false_discovery_rate": round(ungoverned_claims / n_valid, 4) if n_valid else None,
            "governed_false_discovery_rate": round(governed_claims / n_valid, 4) if n_valid else None,
            "definition": "fraction of null splits where the agent reports >=1 DE gene at FDR<0.05",
        },
    }

    print("\n" + "=" * 60)
    print("RESULTS  (false-positive GENES per null split; truth = 0)")
    print("=" * 60)
    l1 = results["layer1_false_positive_genes"]
    print(f"  PER-CELL (ungoverned):   raw p<0.05 mean={l1['per_cell_raw_p']['mean']:>7} | "
          f"FDR<0.05 mean={l1['per_cell_fdr']['mean']}")
    print(f"  PSEUDOBULK (governed):   raw p<0.05 mean={l1['pseudobulk_raw_p']['mean']:>7} | "
          f"FDR<0.05 mean={l1['pseudobulk_fdr']['mean']}")
    l2 = results["layer2_agent_claim_rate"]
    print(f"  Ungoverned agent false-discovery rate: {l2['ungoverned_false_discovery_rate']:.1%}")
    print(f"  Governed agent   false-discovery rate: {l2['governed_false_discovery_rate']:.1%}")

    # Unique filename per run so a sweep never overwrites earlier results.
    import re
    tissue = re.sub(r"[^a-zA-Z0-9]+", "", data_path.stem.split("annotations-")[-1]) or "data"
    ct_slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(cell_type).strip().lower()).strip("_")
    stem = f"null_{tissue}_{ct_slug}"

    (OUT_DIR / f"{stem}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved: {OUT_DIR / (stem + '.json')}")
    _write_report(results, stem)
    return results


def _write_report(r: dict, stem: str = "null_harness"):
    l1 = r["layer1_false_positive_genes"]
    l2 = r["layer2_agent_claim_rate"]
    lines = [
        "# Null Harness (gene-level) - Pseudoreplication False Discovery",
        "",
        "## Setup",
        "",
        f"- Dataset: {r['dataset']}",
        f"- Cell type: {r['cell_type']}",
        f"- Biological replicates (mice): {r['n_biological_replicates']} (groups of {r['group_size']})",
        f"- Genes tested: {r['n_genes_tested']}",
        f"- Null permutations: {r['n_permutations_valid']}",
        f"- alpha = {r['alpha']}",
        "",
        f"**Truth: {r['truth']}.** Every reported DE gene is a false positive.",
        "",
        "## Layer 1 - false-positive genes per null split",
        "",
        "| Method | Statistical unit | FP genes (raw p<0.05) | FP genes (FDR<0.05) |",
        "|--------|------------------|----------------------:|--------------------:|",
        f"| Per-cell Wilcoxon (ungoverned) | cell | {l1['per_cell_raw_p']['mean']} | **{l1['per_cell_fdr']['mean']}** |",
        f"| Pseudobulk t-test (governed) | biological replicate | {l1['pseudobulk_raw_p']['mean']} | {l1['pseudobulk_fdr']['mean']} |",
        "",
        "## Layer 2 - agent false-discovery rate",
        "",
        f"- Ungoverned agent reports >=1 DE gene on **{l2['ungoverned_false_discovery_rate']:.1%}** of null splits",
        f"- Governed agent reports >=1 DE gene on **{l2['governed_false_discovery_rate']:.1%}** of null splits",
        "",
        "## Interpretation",
        "",
        "On data with no real difference, the per-cell test treats correlated cells "
        "within a mouse as independent observations and reports large numbers of "
        "false-positive genes - the pseudoreplication failure (Squair et al. 2021). "
        "An ungoverned agent that runs per-cell differential expression reports these "
        "as discoveries. The governed agent aggregates to biological replicates "
        "(pseudobulk), collapsing the false discoveries to near zero.",
    ]
    (OUT_DIR / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {OUT_DIR / (stem + '.md')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    ap.add_argument("--cell-type", type=str, default="")
    ap.add_argument("--n-perm", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--restrict-age", type=str, default=None)
    args = ap.parse_args()
    run(Path(args.data), args.cell_type, args.n_perm, args.seed, args.restrict_age)
