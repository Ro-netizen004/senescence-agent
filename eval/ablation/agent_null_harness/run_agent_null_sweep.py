"""
Multi-tissue agent null sweep (paper-scale companion to run_null_sweep.py).

Runs ``agent_null_sweep.run_sweep`` across TMS tissues and top cell types.

Usage (from repo root):
    backend\\venv\\Scripts\\python.exe eval/ablation/agent_null_harness/run_agent_null_sweep.py ^
        --n-perm 20 --top 1

    # Quick smoke across all tissues, 3 permutations each:
    backend\\venv\\Scripts\\python.exe eval/ablation/agent_null_harness/run_agent_null_sweep.py ^
        --n-perm 3 --top 1 --arm governed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

import pandas as pd
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from agent_null_sweep import run_sweep, _slug  # noqa: E402
from null_builder import MIN_CELLS_PER_SAMPLE  # noqa: E402

DATA_DIR = ROOT / "backend" / "data"
OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TISSUES = [
    "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Liver.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Aorta.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Limb_Muscle.h5ad",
]

MIN_MICE = 4


def _candidate_cell_types(path: Path, top: int) -> list[str]:
    import scanpy as sc

    ad = sc.read_h5ad(str(path), backed="r")
    obs = ad.obs
    ct_col = "cell_ontology_class" if "cell_ontology_class" in obs.columns else "cell_type"
    sample_col = "mouse.id" if "mouse.id" in obs.columns else "sample_id"
    counts = obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
    mice_ge = (counts >= MIN_CELLS_PER_SAMPLE).sum(axis=1)
    keep = mice_ge[mice_ge >= MIN_MICE].sort_values(ascending=False)
    try:
        ad.file.close()
    except Exception:
        pass
    return keep.index[:top].tolist()


def main():
    ap = argparse.ArgumentParser(description="Multi-tissue agent null sweep")
    ap.add_argument("--n-perm", type=int, default=10)
    ap.add_argument("--top", type=int, default=1, help="cell types per tissue")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--arm", choices=("governed", "ungoverned"), default="governed")
    ap.add_argument("--mode", choices=("homogeneous", "random"), default="homogeneous")
    args = ap.parse_args()

    rows = []
    for fname in TISSUES:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"SKIP (missing): {fname}")
            continue

        tissue = fname.split("annotations-")[-1].replace(".h5ad", "")
        try:
            cell_types = _candidate_cell_types(path, args.top)
        except Exception as exc:
            print(f"SKIP {tissue}: {exc}")
            continue

        print(f"\n{'#' * 60}\n# {tissue}: {cell_types}\n{'#' * 60}")
        for ct in cell_types:
            print(f"\n>>> {tissue} / {ct}")
            try:
                summary = run_sweep(
                    data_path=path,
                    cell_type=ct,
                    n_perm=args.n_perm,
                    seed=args.seed,
                    arm=args.arm,
                    mode=args.mode,
                )
            except Exception as exc:
                print(f"    error: {exc}")
                continue

            ct_slug = _slug(summary["cell_type"])
            stem = f"agent_null_{tissue}_{ct_slug}_{args.arm}"
            (OUT_DIR / f"{stem}.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )

            rows.append({
                "tissue": tissue,
                "cell_type": summary["cell_type"],
                "arm": args.arm,
                "n_perm": summary["n_perm_completed"],
                "ran_deseq2": summary["n_perm_ran_deseq2"],
                "mean_fp_genes": summary["mean_fp_genes"],
                "false_discovery_rate": summary["false_discovery_rate"],
                "routing_miss": summary["n_perm_routing_miss"],
            })

    if not rows:
        print("\nNo runs completed.")
        return

    df = pd.DataFrame(rows)
    arm_slug = args.arm
    csv_path = OUT_DIR / f"agent_null_sweep_summary_{arm_slug}.csv"
    df.to_csv(csv_path, index=False)

    lines = [
        "# Agent Null Sweep — Summary",
        "",
        f"Arm: **{args.arm}** | mode: {args.mode} | permutations each: {args.n_perm}",
        "",
        "| Tissue | Cell type | Ran DESeq2 | Mean FP genes | FDR rate | Routing miss |",
        "|--------|-----------|----------:|--------------:|---------:|-------------:|",
    ]
    for _, r in df.iterrows():
        fdr = r["false_discovery_rate"]
        fdr_s = f"{fdr:.0%}" if fdr is not None else "NA"
        fp = r["mean_fp_genes"]
        fp_s = f"{fp:.2f}" if fp is not None else "NA"
        lines.append(
            f"| {r['tissue']} | {r['cell_type']} | {r['ran_deseq2']} | "
            f"{fp_s} | {fdr_s} | {r['routing_miss']} |"
        )
    if df["mean_fp_genes"].notna().any():
        lines += [
            "",
            f"**Mean FP genes (across configs): {df['mean_fp_genes'].mean():.2f}**",
            f"**Mean false-discovery rate: {df['false_discovery_rate'].mean():.1%}**",
        ]

    md_path = OUT_DIR / f"agent_null_sweep_summary_{arm_slug}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'=' * 60}\nMULTI-TISSUE AGENT NULL SWEEP COMPLETE")
    print(f"Saved: {csv_path}")
    print(f"Saved: {md_path}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
