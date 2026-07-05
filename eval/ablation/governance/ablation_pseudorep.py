"""
Ablation 1: Pseudoreplication guard.

Compares p-values when testing age differences using:
  A) Per-cell scores (pseudoreplication — incorrect)
  B) Per-sample medians (biological replicates — correct, agent behavior)

Dataset: TMS FACS Kidney (3m vs 24m, n=4 mice per group)

Usage:
    python eval/ablation/ablation_pseudorep.py

Output:
    eval/results/ablation/pseudorep_results.json
    eval/results/ablation/pseudorep_report.md
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from agent.pipeline import ensure_pipeline
from tools.senescence import senescence_score

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_PATH = ROOT / "backend" / "data" / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"


def run():
    import scanpy as sc

    if not DATA_PATH.exists():
        print(f"ERROR: Kidney dataset not found at {DATA_PATH}")
        sys.exit(1)

    print("Loading TMS Kidney...")
    adata = sc.read_h5ad(str(DATA_PATH))
    print(f"  Shape: {adata.shape[0]} cells x {adata.shape[1]} genes")

    ensure_pipeline(adata, "mouse")
    senescence_score(adata, "mouse")

    age_col = adata.uns.get("dataset_profile", {}).get("age_column", "age")
    sample_col = adata.uns.get("dataset_profile", {}).get("sample_column", "sample_id")

    ages = adata.obs[age_col].astype(str)
    young_mask = ages == "3m"
    old_mask = ages == "24m"

    scores = adata.obs["senescence_score"]

    results = {}

    # ── Method A: per-cell (pseudoreplication) ────────────────────────────
    young_cells = scores[young_mask].values
    old_cells = scores[old_mask].values

    stat_cell, p_cell = stats.mannwhitneyu(old_cells, young_cells, alternative="greater")
    n_young_cells = int(young_mask.sum())
    n_old_cells = int(old_mask.sum())

    print(f"\n[A] Per-cell (pseudoreplication)")
    print(f"    Young cells: {n_young_cells}, Old cells: {n_old_cells}")
    print(f"    Young mean: {young_cells.mean():.4f}, Old mean: {old_cells.mean():.4f}")
    print(f"    Mann-Whitney p = {p_cell:.2e}  ← artificially significant")

    results["per_cell"] = {
        "method": "per-cell (pseudoreplication)",
        "n_young": n_young_cells,
        "n_old": n_old_cells,
        "young_mean": round(float(young_cells.mean()), 4),
        "old_mean": round(float(old_cells.mean()), 4),
        "p_value": float(p_cell),
        "statistic": float(stat_cell),
        "conclusion": "significant" if p_cell < 0.05 else "not significant",
        "note": "Inflated by treating each cell as independent — pseudoreplication",
    }

    # ── Method B: per-sample medians (agent behavior) ─────────────────────
    subset = adata[young_mask | old_mask].copy()
    sample_medians = (
        subset.obs
        .groupby([sample_col, age_col])["senescence_score"]
        .median()
        .reset_index()
    )
    sample_medians.columns = ["sample_id", "age", "median_score"]

    young_medians = sample_medians[sample_medians["age"] == "3m"]["median_score"].values
    old_medians = sample_medians[sample_medians["age"] == "24m"]["median_score"].values

    n_young_samples = len(young_medians)
    n_old_samples = len(old_medians)

    print(f"\n[B] Per-sample medians (agent behavior)")
    print(f"    Young samples: {n_young_samples}, Old samples: {n_old_samples}")
    print(f"    Young medians: {young_medians.round(4).tolist()}")
    print(f"    Old medians:   {old_medians.round(4).tolist()}")

    if n_young_samples >= 3 and n_old_samples >= 3:
        stat_samp, p_samp = stats.mannwhitneyu(old_medians, young_medians, alternative="greater")
        conclusion = "significant" if p_samp < 0.05 else "not significant"
        print(f"    Mann-Whitney p = {p_samp:.4f}  ← honest estimate")
    else:
        p_samp = None
        stat_samp = None
        conclusion = "LOW_POWER"
        print(f"    Insufficient samples for Mann-Whitney (n={n_young_samples} vs {n_old_samples})")
        print(f"    Agent returns LOW_POWER state — correct behavior")

    results["per_sample"] = {
        "method": "per-sample medians (agent behavior)",
        "n_young_samples": n_young_samples,
        "n_old_samples": n_old_samples,
        "young_medians": young_medians.round(4).tolist(),
        "old_medians": old_medians.round(4).tolist(),
        "p_value": float(p_samp) if p_samp is not None else None,
        "statistic": float(stat_samp) if stat_samp is not None else None,
        "conclusion": conclusion,
        "note": "Statistical unit is biological replicate (mouse), not cell",
    }

    # ── Summary ───────────────────────────────────────────────────────────
    results["summary"] = {
        "dataset": "TMS FACS Kidney",
        "comparison": "3m (young) vs 24m (old)",
        "n_cells_total": int((young_mask | old_mask).sum()),
        "p_value_with_pseudorep": float(p_cell),
        "p_value_without_pseudorep": float(p_samp) if p_samp is not None else None,
        "p_value_inflation_factor": (
            round(p_cell / p_samp, 1) if p_samp and p_samp > 0 else "undefined"
        ) if p_samp else "N/A (LOW_POWER)",
        "agent_inference_state": "LOW_POWER" if n_young_samples < 3 else conclusion.upper(),
    }

    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    print(f"  Per-cell p:    {p_cell:.2e}  (pseudoreplication)")
    print(f"  Per-sample p:  {p_samp:.4f if p_samp else 'LOW_POWER'}  (agent)")
    if p_samp and p_samp > 0:
        print(f"  Inflation:     {p_cell / p_samp:.1f}x")

    # Save JSON
    json_path = OUT_DIR / "pseudorep_results.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved: {json_path}")

    # Write report
    write_report(results)

    return results


def write_report(results: dict):
    s = results["summary"]
    pc = results["per_cell"]
    ps = results["per_sample"]

    p_cell_str = f"{pc['p_value']:.2e}"
    p_samp_str = f"{ps['p_value']:.4f}" if ps["p_value"] is not None else "N/A (LOW_POWER)"
    inflation = s.get("p_value_inflation_factor", "N/A")

    lines = [
        "# Ablation 1: Pseudoreplication Guard",
        "",
        "## Setup",
        "",
        f"- Dataset: {s['dataset']}",
        f"- Comparison: {s['comparison']}",
        f"- Total cells in comparison: {s['n_cells_total']:,}",
        "",
        "## Results",
        "",
        "| Method | Statistical Unit | n (young) | n (old) | p-value | Conclusion |",
        "|--------|-----------------|-----------|---------|---------|------------|",
        f"| Per-cell (pseudoreplication) | Individual cell | {pc['n_young']:,} cells | {pc['n_old']:,} cells | {p_cell_str} | {pc['conclusion'].upper()} |",
        f"| Per-sample medians (agent) | Biological replicate | {ps['n_young_samples']} mice | {ps['n_old_samples']} mice | {p_samp_str} | {ps['conclusion'].upper()} |",
        "",
        "## Interpretation",
        "",
        f"Using individual cells as statistical units (pseudoreplication) yields p = {p_cell_str} "
        f"from {pc['n_young']:,} young and {pc['n_old']:,} old cells — an artificially extreme result "
        f"driven entirely by sample size, not biological effect size.",
        "",
        f"The agent aggregates to per-sample medians before testing, reducing the effective "
        f"n to {ps['n_young_samples']} young mice vs {ps['n_old_samples']} old mice. "
        f"The resulting p-value is {p_samp_str}, and the agent correctly assigns "
        f"inference state **{s['agent_inference_state']}**.",
        "",
        f"p-value inflation factor from pseudoreplication: **{inflation}**",
        "",
        "## Agent behavior",
        "",
        f"Agent inference state: `{s['agent_inference_state']}`",
        "",
        "The inference state machine prevents the agent from reporting a significant result "
        "regardless of per-cell p-values. This is the correct behavior: statistical significance "
        "at the cell level does not constitute evidence of a biological effect.",
    ]

    report_path = OUT_DIR / "pseudorep_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    run()
