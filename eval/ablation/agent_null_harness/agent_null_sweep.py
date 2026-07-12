"""
Agent-level null sweep: run the real ``run_agent`` on constructed nulls.

Unlike ``null_harness.py`` (isolated Wilcoxon vs t-test), this exercises the
deployed agent path: routing, admissibility, DESeq2 tool, inference state, and
deterministic renderer.

Usage (from repo root):
    backend\\venv\\Scripts\\python.exe eval/ablation/agent_null_harness/agent_null_sweep.py ^
        --cell-type "fenestrated cell" --n-perm 10

    # Ungoverned ablation arm (needs GEMINI_API_KEY):
    backend\\venv\\Scripts\\python.exe eval/ablation/agent_null_harness/agent_null_sweep.py ^
        --arm ungoverned --n-perm 5

Outputs:
    eval/results/ablation/agent_null_<tissue>_<celltype>_<arm>.json
    eval/results/ablation/agent_null_<tissue>_<celltype>_<arm>.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from null_builder import build_null_adata, FAKE_OLD, FAKE_YOUNG  # noqa: E402

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DATA = (
    ROOT / "backend" / "data" / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
)

# Deterministic Tier-1 DESeq2 template (no Gemini required when governed).
def deseq2_prompt(cell_type: str) -> str:
    return (
        f"Run differential expression on {cell_type} "
        f"between {FAKE_YOUNG} and {FAKE_OLD}"
    )


def score_agent_result(res: dict) -> dict:
    """Extract false-discovery facts from a run_agent response."""
    tool_calls = res.get("tool_calls") or []
    deseq2 = next((t for t in tool_calls if t.get("name") == "run_deseq2"), None)

    if not deseq2:
        return {
            "ran_deseq2": False,
            "blocked": False,
            "n_sig": None,
            "inference_state": None,
            "false_discovery": None,
            "error": "run_deseq2 not called (routing miss)",
        }

    result = deseq2.get("result") or {}
    if result.get("error"):
        return {
            "ran_deseq2": False,
            "blocked": result.get("error") == "inadmissible_inference",
            "n_sig": None,
            "inference_state": "BLOCKED",
            "false_discovery": False,
            "error": result.get("message") or result.get("error"),
        }

    n_sig = int(result.get("n_significant_fdr_0_05") or 0)
    state = (result.get("inference_state") or {}).get("state")
    if not state and isinstance(result.get("inference_state"), str):
        state = result.get("inference_state")

    # Inferential overclaim on a null: licensed significance, not raw gene counts.
    false_discovery = state == "SIGNIFICANT_INFERENTIAL"
    exploratory_fp = n_sig > 0 and state == "LOW_POWER"

    return {
        "ran_deseq2": True,
        "blocked": False,
        "n_sig": n_sig,
        "inference_state": state,
        "false_discovery": false_discovery,
        "exploratory_fp": exploratory_fp,
        "n_samples": result.get("n_samples"),
        "samples_per_age": result.get("samples_per_age"),
        "error": None,
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(text).strip().lower()).strip("_")


def run_sweep(
    data_path: Path,
    cell_type: str,
    n_perm: int,
    seed: int,
    arm: str,
    mode: str,
    file_id: str = "agent_null_eval",
) -> dict:
    from agent.agent import run_agent
    from agent.cache import cache_adata
    from agent.pipeline import ensure_pipeline

    governed = arm == "governed"
    os.environ["AGENT_GOVERNANCE"] = "on" if governed else "off"

    if not governed and not os.getenv("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY not set — ungoverned arm may fail.")

    resolved_ct = cell_type or None
    prompt = deseq2_prompt(resolved_ct) if resolved_ct else None
    rows = []

    print(f"Dataset: {data_path.name}")
    print(f"Arm: {arm} | mode: {mode} | permutations: {n_perm}")
    print(f"Truth: 0 DE genes (constructed null)\n")

    for i in range(n_perm):
        perm_seed = seed + i
        try:
            sub, meta = build_null_adata(
                data_path, resolved_ct or cell_type, perm_seed, mode=mode
            )
        except ValueError as exc:
            print(f"perm {i}: SKIP — {exc}")
            rows.append({"perm": i, "seed": perm_seed, "skipped": True, "error": str(exc)})
            continue

        if resolved_ct != meta["cell_type"]:
            resolved_ct = meta["cell_type"]
        if prompt is None:
            prompt = deseq2_prompt(resolved_ct)

        cache_adata(file_id, sub)
        ensure_pipeline(sub, "mouse")

        print(f"perm {i}/{n_perm - 1} seed={perm_seed} "
              f"mice={meta['n_mice']} cells={meta['n_cells']} ...", flush=True)

        try:
            res = run_agent([], prompt, file_id, "mouse")
        except Exception as exc:
            rows.append({
                "perm": i,
                "seed": perm_seed,
                "meta": meta,
                "skipped": False,
                "agent_error": str(exc),
                "false_discovery": None,
            })
            print(f"  ERROR: {exc}")
            continue

        scored = score_agent_result(res)
        rows.append({
            "perm": i,
            "seed": perm_seed,
            "meta": meta,
            "skipped": False,
            **scored,
        })
        print(
            f"  ran_deseq2={scored['ran_deseq2']} n_sig={scored['n_sig']} "
            f"state={scored['inference_state']} inferential_fp={scored['false_discovery']} "
            f"exploratory_fp={scored.get('exploratory_fp')}"
        )

    valid = [r for r in rows if r.get("false_discovery") is not None]
    sig_rows = [r for r in valid if r.get("ran_deseq2")]

    summary = {
        "dataset": data_path.name,
        "cell_type": resolved_ct,
        "arm": arm,
        "mode": mode,
        "prompt": prompt,
        "n_perm_requested": n_perm,
        "n_perm_completed": len(valid),
        "n_perm_ran_deseq2": len(sig_rows),
        "n_perm_blocked": sum(1 for r in valid if r.get("blocked")),
        "n_perm_routing_miss": sum(1 for r in valid if r.get("error") == "run_deseq2 not called (routing miss)"),
        "mean_fp_genes": (
            round(sum(r["n_sig"] for r in sig_rows) / len(sig_rows), 2) if sig_rows else None
        ),
        "false_discovery_rate": (
            round(sum(r["false_discovery"] for r in sig_rows) / len(sig_rows), 4)
            if sig_rows else None
        ),
        "exploratory_fp_rate": (
            round(sum(r.get("exploratory_fp") for r in sig_rows) / len(sig_rows), 4)
            if sig_rows else None
        ),
        "truth": "null (random mouse-to-group split); expected DE genes = 0",
        "permutations": rows,
    }
    return summary


def _write_report(summary: dict, stem: str) -> None:
    lines = [
        "# Agent Null Sweep",
        "",
        f"- Dataset: {summary['dataset']}",
        f"- Cell type: {summary['cell_type']}",
        f"- Arm: **{summary['arm']}**",
        f"- Null mode: {summary['mode']}",
        f"- Prompt: `{summary['prompt']}`",
        f"- Permutations completed: {summary['n_perm_completed']} / {summary['n_perm_requested']}",
        "",
        "## Results",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| DESeq2 ran | {summary['n_perm_ran_deseq2']} |",
        f"| Blocked | {summary['n_perm_blocked']} |",
        f"| Routing miss | {summary['n_perm_routing_miss']} |",
        f"| Mean FP genes (FDR<0.05) | {summary['mean_fp_genes']} |",
        f"| False-discovery rate (inferential) | {summary['false_discovery_rate']} |",
        f"| Exploratory FP rate (LOW_POWER, n_sig>0) | {summary.get('exploratory_fp_rate')} |",
        "",
        "**Truth = 0 DE genes.** Any significant DESeq2 result is a false positive.",
        "",
        "## Interpretation",
        "",
        "This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + "
        "inference state), not the isolated Wilcoxon/t-test null harness.",
    ]
    (OUT_DIR / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Agent-level constructed-null sweep")
    ap.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    ap.add_argument("--cell-type", type=str, default="", help="defaults to most abundant type")
    ap.add_argument("--n-perm", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--arm",
        choices=("governed", "ungoverned"),
        default="governed",
        help="governed uses AGENT_GOVERNANCE=on (production path)",
    )
    ap.add_argument(
        "--mode",
        choices=("homogeneous", "random"),
        default="homogeneous",
        help="homogeneous = same age/sex stratum; random = null-harness style",
    )
    args = ap.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")

    summary = run_sweep(
        data_path=data_path,
        cell_type=args.cell_type,
        n_perm=args.n_perm,
        seed=args.seed,
        arm=args.arm,
        mode=args.mode,
    )

    tissue = re.sub(
        r"[^a-zA-Z0-9]+", "", data_path.stem.split("annotations-")[-1]
    ) or "data"
    ct_slug = _slug(summary["cell_type"] or "auto")
    stem = f"agent_null_{tissue}_{ct_slug}_{args.arm}"

    json_path = OUT_DIR / f"{stem}.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_report(summary, stem)

    print("\n" + "=" * 60)
    print("AGENT NULL SWEEP COMPLETE")
    print(f"  Mean FP genes:     {summary['mean_fp_genes']}")
    print(f"  False-discovery rate (inferential): {summary['false_discovery_rate']}")
    print(f"  Exploratory FP rate (LOW_POWER):    {summary.get('exploratory_fp_rate')}")
    print(f"  Saved: {json_path}")
    print(f"  Saved: {OUT_DIR / (stem + '.md')}")


if __name__ == "__main__":
    main()
