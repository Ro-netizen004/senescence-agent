"""End-to-end governed positive control using a real TMS biological contrast."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
os.environ["AGENT_EVAL_DIAGNOSTICS"] = "1"
os.environ["AGENT_GOVERNANCE"] = "on"

from agent.agent import run_agent  # noqa: E402
from agent.cache import cache_adata  # noqa: E402
from agent.pipeline import ensure_pipeline  # noqa: E402
from tools.gene_utils import SENESCENCE_GENES_MOUSE  # noqa: E402

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _slug(value):
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(value).strip().lower()).strip("_")


def run_positive_control(data_path, cell_type, reference, comparison):
    import scanpy as sc

    adata = sc.read_h5ad(str(data_path))
    ensure_pipeline(adata, "mouse")
    file_id = f"positive-control-{_slug(data_path.stem)}-{_slug(cell_type)}"
    cache_adata(file_id, adata)
    prompt = (
        f"Run differential expression on {cell_type} between {reference} and "
        f"{comparison} using age as the grouping variable."
    )
    response = run_agent([], prompt, file_id, "mouse")
    calls = response.get("tool_calls") or []
    call = next((c for c in calls if c.get("name") == "run_deseq2"), None)
    if not call:
        return {
            "status": "routing_failure", "prompt": prompt,
            "reply": response.get("reply"), "tool_calls": calls,
        }
    result = call.get("result") or {}
    state_record = result.get("inference_state") or {}
    state = state_record.get("state") if isinstance(state_record, dict) else state_record
    diagnostics = result.get("evaluation_diagnostics") or {}
    significant = diagnostics.get("significant_genes") or [
        str(row.get("gene")) for row in result.get("results") or []
        if row.get("padj") is not None and float(row["padj"]) < 0.05
    ]
    senmayo = sorted(set(significant) & set(SENESCENCE_GENES_MOUSE))
    stability = result.get("replicate_stability") or {}
    plausibility = result.get("result_plausibility") or {}
    n_significant = result.get("n_significant_fdr_0_05")
    if n_significant is None:
        n_significant = stability.get("n_significant_genes", len(significant))
    n_significant = int(n_significant or 0)
    licensed = state == "SIGNIFICANT_INFERENTIAL"
    criteria = {
        "correct_tool_routed": True,
        "deseq2_completed": not bool(result.get("error")),
        "significant_genes_present": n_significant > 0,
        "plausibility_passed": plausibility.get("verdict") == "ok",
        "replicate_stability_passed": stability.get("verdict") == "stable",
        "inferential_claim_licensed": licensed,
    }
    return {
        "status": "passed" if all(criteria.values()) else "did_not_pass",
        "dataset": data_path.name,
        "cell_type": cell_type,
        "group_column": "age",
        "reference_group": reference,
        "comparison_group": comparison,
        "prompt": prompt,
        "criteria": criteria,
        "inference_state": state,
        "n_significant_fdr_0_05": n_significant,
        "samples_per_group": result.get("samples_per_group"),
        "result_plausibility": plausibility,
        "replicate_stability": stability,
        "senmayo_overlap_count": len(senmayo),
        "senmayo_overlap_genes": senmayo,
        "reply": response.get("reply"),
    }


def main():
    parser = argparse.ArgumentParser(description="Governed TMS positive control")
    parser.add_argument(
        "--data", default=str(ROOT / "backend" / "data" /
        "tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad")
    )
    parser.add_argument("--cell-type", default="B cell")
    parser.add_argument("--reference", default="3m")
    parser.add_argument("--comparison", default="24m")
    args = parser.parse_args()
    result = run_positive_control(
        Path(args.data), args.cell_type, args.reference, args.comparison
    )
    tissue = Path(args.data).stem.split("annotations-")[-1]
    stem = (
        f"agent_positive_{tissue}_{_slug(args.cell_type)}_"
        f"{_slug(args.reference)}_vs_{_slug(args.comparison)}"
    )
    json_path = OUT_DIR / f"{stem}.json"
    md_path = OUT_DIR / f"{stem}.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    criteria = result.get("criteria") or {}
    lines = [
        "# Governed Agent Positive Control", "",
        f"- Dataset: {result.get('dataset')}",
        f"- Cell type: {result.get('cell_type')}",
        f"- Contrast: {result.get('reference_group')} vs {result.get('comparison_group')}",
        f"- Status: **{result.get('status')}**", "", "## Criteria", "",
    ]
    lines.extend(f"- {name}: **{value}**" for name, value in criteria.items())
    lines += [
        "", "## Result", "",
        f"- Inference state: {result.get('inference_state')}",
        f"- Samples per group: {result.get('samples_per_group')}",
        f"- Significant genes: {result.get('n_significant_fdr_0_05')}",
        f"- Plausibility: {result.get('result_plausibility')}",
        f"- Replicate stability verdict: "
        f"{(result.get('replicate_stability') or {}).get('verdict')}",
        f"- Stable significant genes: "
        f"{(result.get('replicate_stability') or {}).get('n_stable_genes')} / "
        f"{(result.get('replicate_stability') or {}).get('n_significant_genes')}",
        f"- Stable-gene fraction: "
        f"{(result.get('replicate_stability') or {}).get('stable_gene_fraction')}",
        f"- Median minimum effect retention: "
        f"{(result.get('replicate_stability') or {}).get('median_minimum_effect_retention')}",
        f"- SenMayo overlap ({result.get('senmayo_overlap_count')}): "
        f"{result.get('senmayo_overlap_genes')}",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")
    raise SystemExit(0 if result.get("status") == "passed" else 1)


if __name__ == "__main__":
    main()
