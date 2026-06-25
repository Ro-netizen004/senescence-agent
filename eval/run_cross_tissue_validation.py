"""
Cross-tissue TMS validation harness.

Runs the standard senescence panel on multiple TMS FACS tissues and
produces a comparison table for the paper.

Usage:
    python eval/run_cross_tissue_validation.py

Outputs:
    eval/results/cross_tissue/cross_tissue_metrics.csv
    eval/results/cross_tissue/cross_tissue_report.md
"""

import sys
import json
import warnings
from pathlib import Path

import pandas as pd
import scanpy as sc

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from agent.pipeline import ensure_pipeline
from tools.senescence import senescence_score, find_senescence_markers
from tools.age_analysis import compare_across_age
from agent.inference_state import apply_inference_state

OUT_DIR = ROOT / "eval" / "results" / "cross_tissue"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Dataset registry ──────────────────────────────────────────────────────
# Update paths to wherever you saved the TMS files
TMS_BASE = ROOT / "backend" / "data"

DATASETS = [
    {
        "label": "Kidney",
        "path": TMS_BASE / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad",
        "species": "mouse",
    },
    {
        "label": "Liver",
        "path": TMS_BASE / "tabula-muris-senis-facs-processed-official-annotations-Liver.h5ad",
        "species": "mouse",
    },
    {
        "label": "Spleen",
        "path": TMS_BASE / "tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad",
        "species": "mouse",
    },
    {
        "label": "Aorta",
        "path": TMS_BASE / "tabula-muris-senis-facs-processed-official-annotations-Aorta.h5ad",
        "species": "mouse",
    },
    {
        "label": "Limb_Muscle",
        "path": TMS_BASE / "tabula-muris-senis-facs-processed-official-annotations-Limb_Muscle.h5ad",
        "species": "mouse",
    },
]


# ── Per-dataset analysis ──────────────────────────────────────────────────

def run_one_dataset(label: str, path: Path, species: str) -> dict:
    print(f"\n{'='*60}")
    print(f"Processing: {label}")
    print(f"{'='*60}")

    if not path.exists():
        print(f"  SKIPPED — file not found: {path}")
        return {"label": label, "status": "missing", "path": str(path)}

    print(f"  Loading {path.name}...")
    try:
        adata = sc.read_h5ad(str(path))
    except OSError as e:
        print(f"  SKIPPED — file corrupted or incomplete: {e}")
        return {"label": label, "status": "corrupted", "path": str(path)}
    print(f"  Shape: {adata.shape[0]} cells x {adata.shape[1]} genes")

    # Run pipeline
    ensure_pipeline(adata, species)
    profile = adata.uns.get("dataset_profile") or {}

    age_col = profile.get("age_column") or "age"
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    youngest = profile.get("youngest")
    oldest = profile.get("oldest")
    age_values = profile.get("age_values") or []

    print(f"  Profile: age_col={age_col}, youngest={youngest}, oldest={oldest}")
    print(f"  Age values: {age_values}")
    print(f"  Cell type col: {ct_col}")
    if ct_col in adata.obs.columns:
        cell_types = adata.obs[ct_col].astype(str).unique().tolist()
        print(f"  Cell types ({len(cell_types)}): {cell_types[:5]}{'...' if len(cell_types) > 5 else ''}")

    # 1. Marker coverage
    marker_result = find_senescence_markers(adata, species)
    coverage_pct = marker_result.get("coverage_pct")
    genes_used = len(marker_result.get("found_markers") or [])
    print(f"  SenMayo coverage: {coverage_pct}% ({genes_used} genes)")

    # 2. Senescence score
    score_result = senescence_score(adata, species)
    mean_score = score_result.get("mean_score")
    max_score = score_result.get("max_score")
    top_cell_type = score_result.get("top_senescent_cell_type")
    top_cluster = score_result.get("top_senescent_cluster")
    print(f"  Mean score: {mean_score}, Max: {max_score}")
    print(f"  Top senescent: cluster {top_cluster} ({top_cell_type})")

    # 3. Age trend (all cell types)
    age_result = {}
    age_trend_direction = "unknown"
    youngest_median = oldest_median = None

    try:
        age_result = compare_across_age(adata, age_col, ct_col, species)
        # global (no cell_type) stores under global_senescence_by_age
        by_age = age_result.get("senescence_by_age") or age_result.get("global_senescence_by_age") or {}

        if youngest and oldest and youngest in by_age and oldest in by_age:
            youngest_median = by_age[youngest]
            oldest_median = by_age[oldest]
            if oldest_median > youngest_median:
                age_trend_direction = "increasing"
            elif oldest_median < youngest_median:
                age_trend_direction = "decreasing"
            else:
                age_trend_direction = "flat"
            print(f"  Age trend: {youngest}={youngest_median:.4f} → {oldest}={oldest_median:.4f} ({age_trend_direction})")
    except Exception as e:
        print(f"  Age comparison failed: {e}")

    # 4. Top cell types — derived from per-cell-type median scores (single consistent source)
    most_senescent = age_result.get("most_senescent_per_celltype") or {}
    top_ranked = sorted(most_senescent.items(), key=lambda x: x[1].get("score", 0), reverse=True)
    top_3 = top_ranked[:3]
    # Use same source for top_1 so it matches top_3 ordering
    top_celltype_from_age = top_ranked[0][0] if top_ranked else top_cell_type

    row = {
        "label": label,
        "status": "ok",
        "n_cells": adata.n_obs,
        "n_genes": adata.n_vars,
        "n_cell_types": adata.obs[ct_col].nunique() if ct_col in adata.obs.columns else None,
        "age_values": ", ".join(age_values),
        "youngest": youngest,
        "oldest": oldest,
        "coverage_pct": coverage_pct,
        "genes_used": genes_used,
        "mean_score": mean_score,
        "max_score": max_score,
        "top_senescent_cell_type": top_celltype_from_age,
        "youngest_median": round(float(youngest_median), 4) if youngest_median is not None else None,
        "oldest_median": round(float(oldest_median), 4) if oldest_median is not None else None,
        "age_trend": age_trend_direction,
        "top_3_senescent_cell_types": ", ".join(ct for ct, _ in top_3),
    }

    return row


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("CROSS-TISSUE TMS VALIDATION")
    print("=" * 60)

    rows = []
    for ds in DATASETS:
        row = run_one_dataset(ds["label"], Path(ds["path"]), ds["species"])
        rows.append(row)

    df = pd.DataFrame(rows)

    # Save CSV
    csv_path = OUT_DIR / "cross_tissue_metrics.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved: {csv_path}")

    # Print summary table
    ok = df[df["status"] == "ok"]
    print("\n" + "=" * 60)
    print("SUMMARY TABLE")
    print("=" * 60)
    if not ok.empty:
        summary_cols = [
            "label", "n_cells", "coverage_pct", "mean_score",
            "youngest_median", "oldest_median", "age_trend", "top_senescent_cell_type"
        ]
        available = [c for c in summary_cols if c in ok.columns]
        print(ok[available].to_markdown(index=False))

    # Write report
    write_report(df, ok)
    print(f"\nDone. Results in {OUT_DIR}")


def write_report(df: pd.DataFrame, ok: pd.DataFrame):
    missing = df[df["status"] == "missing"]

    lines = [
        "# Cross-Tissue TMS Validation Report",
        "",
        "## Datasets",
        "",
        f"- Tissues attempted: {len(df)}",
        f"- Tissues completed: {len(ok)} / {len(df)}",
        "",
    ]

    if not missing.empty:
        lines.append("### Tissues not analysed (data not available locally)")
        for _, row in missing.iterrows():
            lines.append(f"- {row['label']}: not downloaded — excluded from analysis, not a pipeline failure")
        lines.append("")

    if not ok.empty:
        lines += [
            "## Results",
            "",
            "### Coverage and Scoring",
            "",
            "| Tissue | Cells | Coverage % | Genes Used | Mean Score | Max Score |",
            "|--------|-------|-----------|------------|------------|-----------|",
        ]
        for _, row in ok.iterrows():
            lines.append(
                f"| {row['label']} | {row['n_cells']:,} | {row['coverage_pct']} | "
                f"{row['genes_used']} | {row['mean_score']} | {row['max_score']} |"
            )

        lines += [
            "",
            "### Age Trends (youngest vs oldest)",
            "",
            "| Tissue | Youngest | Oldest | Young Median | Old Median | Trend |",
            "|--------|----------|--------|--------------|------------|-------|",
        ]
        for _, row in ok.iterrows():
            lines.append(
                f"| {row['label']} | {row['youngest']} | {row['oldest']} | "
                f"{row['youngest_median']} | {row['oldest_median']} | {row['age_trend']} |"
            )

        lines += [
            "",
            "### Top Senescent Cell Types per Tissue",
            "",
            "| Tissue | Top Cell Type | Top 3 |",
            "|--------|--------------|-------|",
        ]
        for _, row in ok.iterrows():
            lines.append(
                f"| {row['label']} | {row['top_senescent_cell_type']} | {row['top_3_senescent_cell_types']} |"
            )

        lines += [
            "",
            "## Notes",
            "",
            "- All datasets: TMS FACS processed official annotations (Tabula Muris Consortium 2020)",
            "- Species: mouse",
            "- Signature: SenMayo 125-gene set (Saul et al. 2022)",
            "- **Scores are relative within each dataset — not directly comparable across tissues**",
            "- Age trend: global median senescence score comparing youngest vs oldest age group",
            "- **Age trends are descriptive only.** Global medians are confounded by age-related shifts in cell-type composition. A tissue where a high-scoring cell type becomes less abundant with age will show a decreasing global trend even if per-cell senescence increases. Cell-type-specific analysis is required to disentangle composition from true senescence accumulation.",
            "- Top senescent cell types are ranked by per-cell-type median score (same source as top-3 column)",
            "- Statistical testing (Mann-Whitney on per-sample medians) not run here — see gold case eval for per-tissue p-values",
        ]

    report_path = OUT_DIR / "cross_tissue_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    main()
