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
import subprocess
import sys
from pathlib import Path

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


def _stem(tissue, cell_type, args):
    return (
        f"agent_null_{tissue}_{_slug(cell_type)}_{args.arm}_{args.mode}_"
        f"{args.design}_{args.prompt_style}_seed{args.seed}_n{args.n_perm}"
    )


def _run_worker(path: Path, tissue: str, cell_type: str, args) -> tuple[dict | None, dict]:
    """Run one cell-type sweep in a fresh interpreter with a hard memory boundary."""
    stem = _stem(tissue, cell_type, args)
    result_path = OUT_DIR / f"{stem}.json"
    log_path = OUT_DIR / f"{stem}.log"
    command = [
        sys.executable, str(Path(__file__).resolve()), "--worker",
        "--data", str(path), "--cell-type", cell_type,
        "--n-perm", str(args.n_perm), "--seed", str(args.seed),
        "--arm", args.arm, "--mode", args.mode, "--design", args.design,
        "--prompt-style", args.prompt_style,
    ]
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(
            command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            text=True, check=False,
        )
    status = {
        "tissue": tissue, "cell_type": cell_type,
        "status": "completed" if completed.returncode == 0 and result_path.exists() else "failed",
        "returncode": completed.returncode, "result_path": str(result_path),
        "log_path": str(log_path),
    }
    if status["status"] == "failed":
        try:
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            status["error_tail"] = tail
        except Exception:
            status["error_tail"] = []
        return None, status
    return json.loads(result_path.read_text(encoding="utf-8")), status


def _worker_main(args):
    path = Path(args.data)
    tissue = path.stem.split("annotations-")[-1]
    summary = run_sweep(
        data_path=path, cell_type=args.cell_type, n_perm=args.n_perm,
        seed=args.seed, arm=args.arm, mode=args.mode, design=args.design,
        prompt_style=args.prompt_style,
    )
    result_path = OUT_DIR / f"{_stem(tissue, summary['cell_type'], args)}.json"
    if summary.get("n_perm_agent_errors", 0):
        partial_path = result_path.with_name(f"{result_path.stem}.partial.json")
        partial_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(
            f"WORKER INCOMPLETE: {summary['n_perm_agent_errors']} agent/API errors; "
            f"partial result saved at {partial_path}"
        )
        raise SystemExit(2)
    temporary = result_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    temporary.replace(result_path)
    print(f"WORKER COMPLETE: {result_path}")


def main():
    ap = argparse.ArgumentParser(description="Multi-tissue agent null sweep")
    ap.add_argument("--n-perm", type=int, default=10)
    ap.add_argument("--top", type=int, default=1, help="cell types per tissue")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--arm",
        choices=("governed", "ungoverned", "governed_same_method", "ungoverned_same_method"),
        default="governed",
    )
    ap.add_argument("--mode", choices=("homogeneous", "random", "stratified"), default="homogeneous")
    ap.add_argument("--design", choices=("valid", "one_sample_per_group", "per_cell_sample", "confounded", "confounded_partial", "covariate_balanced", "contrast_alias", "contrast_alias_with_batch"), default="valid")
    ap.add_argument("--prompt-style", choices=("explicit", "ordinary", "leading", "pseudoreplication_pressure"), default="explicit")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--data", help=argparse.SUPPRESS)
    ap.add_argument("--cell-type", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.worker:
        if not args.data or not args.cell_type:
            ap.error("--worker requires --data and --cell-type")
        _worker_main(args)
        return

    rows = []
    statuses = []
    for fname in TISSUES:
        path = DATA_DIR / fname
        tissue = fname.split("annotations-")[-1].replace(".h5ad", "")
        if not path.exists():
            print(f"SKIP (missing): {fname}")
            statuses.append({"tissue": tissue, "cell_type": None, "status": "missing"})
            continue

        try:
            cell_types = _candidate_cell_types(path, args.top)
        except Exception as exc:
            print(f"SKIP {tissue}: {exc}")
            statuses.append({"tissue": tissue, "cell_type": None, "status": "candidate_error", "error": str(exc)})
            continue
        if not cell_types:
            statuses.append({"tissue": tissue, "cell_type": None, "status": "no_candidate_cell_type"})

        print(f"\n{'#' * 60}\n# {tissue}: {cell_types}\n{'#' * 60}")
        for ct in cell_types:
            print(f"\n>>> {tissue} / {ct}")
            summary, status = _run_worker(path, tissue, ct, args)
            statuses.append(status)
            if summary is None:
                print(f"    FAILED (exit {status['returncode']}): {status['log_path']}")
                continue
            print(f"    completed: {status['result_path']}")

            rows.append({
                "tissue": tissue,
                "cell_type": summary["cell_type"],
                "arm": args.arm,
                "n_perm": summary["n_perm_completed"],
                "ran_deseq2": summary["n_perm_ran_deseq2"],
                "mean_null_discoveries": summary["mean_null_discoveries"],
                "plausibility_withheld_rate": summary["plausibility_withheld_rate"],
                "stability_withheld_rate": summary.get("stability_withheld_rate"),
                "result_withheld_rate": summary.get("result_withheld_rate"),
                "inference_state_counts": json.dumps(summary["inference_state_counts"], sort_keys=True),
                "raw_discovery_rate": summary["raw_discovery_rate"],
                "licensed_claim_rate": summary["licensed_claim_rate"],
                "reply_overclaim_rate": summary["reply_overclaim_rate"],
                "routing_miss": summary["n_perm_routing_miss"],
            })

    arm_slug = (
        f"{args.arm}_{args.mode}_{args.design}_{args.prompt_style}_"
        f"seed{args.seed}_n{args.n_perm}"
    )
    status_path = OUT_DIR / f"agent_null_sweep_status_{arm_slug}.json"
    status_path.write_text(json.dumps(statuses, indent=2), encoding="utf-8")
    if not rows:
        print(f"\nNo runs completed. Status: {status_path}")
        raise SystemExit(1)

    df = pd.DataFrame(rows)
    csv_path = OUT_DIR / f"agent_null_sweep_summary_{arm_slug}.csv"
    df.to_csv(csv_path, index=False)

    lines = [
        "# Agent Null Sweep — Summary",
        "",
        f"Arm: **{args.arm}** | mode: {args.mode} | permutations each: {args.n_perm}",
        f"Worker status: `{status_path.name}`",
        "",
        "| Tissue | Cell type | Ran DESeq2 | Mean null discoveries | Raw discovery | Licensed claim | Any withheld | Stability withheld | Plausibility withheld | Reply overclaim | Routing miss |",
        "|--------|-----------|----------:|----------------------:|--------------:|---------------:|-------------:|-------------------:|----------------------:|----------------:|-------------:|",
    ]
    for _, r in df.iterrows():
        raw_s = f"{r['raw_discovery_rate']:.0%}" if r["raw_discovery_rate"] is not None else "NA"
        licensed_s = f"{r['licensed_claim_rate']:.0%}" if r["licensed_claim_rate"] is not None else "NA"
        reply_s = f"{r['reply_overclaim_rate']:.0%}" if r["reply_overclaim_rate"] is not None else "NA"
        fp = r["mean_null_discoveries"]
        fp_s = f"{fp:.2f}" if fp is not None else "NA"
        withheld_s = f"{r['result_withheld_rate']:.0%}" if r["result_withheld_rate"] is not None else "NA"
        stability_s = f"{r['stability_withheld_rate']:.0%}" if r["stability_withheld_rate"] is not None else "NA"
        plausibility_s = f"{r['plausibility_withheld_rate']:.0%}" if r["plausibility_withheld_rate"] is not None else "NA"
        lines.append(
            f"| {r['tissue']} | {r['cell_type']} | {r['ran_deseq2']} | "
            f"{fp_s} | {raw_s} | {licensed_s} | {withheld_s} | {stability_s} | "
            f"{plausibility_s} | {reply_s} | {r['routing_miss']} |"
        )
    if df["mean_null_discoveries"].notna().any():
        lines += [
            "",
            f"**Mean null discoveries (across configs): {df['mean_null_discoveries'].mean():.2f}**",
            f"**Macro-average raw discovery rate: {df['raw_discovery_rate'].mean():.1%}**",
            f"**Macro-average licensed-claim rate: {df['licensed_claim_rate'].mean():.1%}**",
            f"**Micro-average raw discovery rate: "
            f"{(df['raw_discovery_rate'] * df['ran_deseq2']).sum() / df['ran_deseq2'].sum():.1%}**",
        ]

    md_path = OUT_DIR / f"agent_null_sweep_summary_{arm_slug}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'=' * 60}\nMULTI-TISSUE AGENT NULL SWEEP COMPLETE")
    print(f"Saved: {csv_path}")
    print(f"Saved: {md_path}")
    print(f"Saved: {status_path}")
    print(df.to_string(index=False))
    failures = [s for s in statuses if s.get("status") != "completed"]
    if failures:
        print(f"WARNING: {len(failures)} tissue/cell-type jobs did not complete; see status JSON.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
