"""
Real end-to-end GOVERNED vs UNGOVERNED agent transcripts on a KNOWN-NULL split.

Builds a null condition (whole mice randomly relabeled to two fake ages within a
single cell type, so no true age difference exists), then sends identical prompts
to the two agent configurations via the real `run_agent`:

  - UNGOVERNED (AGENT_GOVERNANCE=off): per-cell tests, no gates, LLM narrates.
  - GOVERNED   (default):              pseudobulk/per-sample, gates + renderer.

Every DE gene or "significant" claim the ungoverned agent makes here is a FALSE
positive by construction. This ties the null-harness simulation to a real agent.

Usage (needs GEMINI_API_KEY in .env; makes a few live LLM calls):
    python eval/ablation/run_ungoverned_agent.py
    python eval/ablation/run_ungoverned_agent.py --cell-type "epithelial cell of proximal tubule" --seed 0
"""

import os
import sys
import argparse
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

DEFAULT_DATA = ROOT / "backend" / "data" / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_CELLS_PER_SAMPLE = 20
FAKE_AGES = ("3m", "24m")


def build_null_adata(data_path: Path, cell_type: str, seed: int):
    import scanpy as sc
    from agent.pipeline import ensure_pipeline
    from tools.build_pseudobulk import _get_sample_column

    adata = sc.read_h5ad(str(data_path))
    ensure_pipeline(adata, "mouse")

    profile = adata.uns.get("dataset_profile") or {}
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    age_col = profile.get("age_column") or "age"
    sample_col = _get_sample_column(adata, profile.get("sample_column") or "sample_id")

    if not cell_type:
        counts = adata.obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
        mice_ge = (counts >= MIN_CELLS_PER_SAMPLE).sum(axis=1)
        cell_type = mice_ge.sort_values(ascending=False).index[0]

    sub = adata[adata.obs[ct_col].astype(str) == str(cell_type)].copy()
    vc = sub.obs[sample_col].astype(str).value_counts()
    mice = sorted(vc[vc >= MIN_CELLS_PER_SAMPLE].index.tolist())
    if len(mice) < 4:
        raise SystemExit(f"Need >=4 mice with >={MIN_CELLS_PER_SAMPLE} cells; {cell_type} has {len(mice)}.")

    rng = np.random.default_rng(seed)
    perm = rng.permutation(mice)
    half = len(mice) // 2
    group_a = set(perm[:half])          # fake "3m"
    group_b = set(perm[half:2 * half])  # fake "24m"

    sub = sub[sub.obs[sample_col].astype(str).isin(group_a | group_b)].copy()
    fake_age = sub.obs[sample_col].astype(str).map(
        lambda m: FAKE_AGES[0] if m in group_a else FAKE_AGES[1]
    )
    sub.obs[age_col] = fake_age.values
    # Refresh the profile so youngest/oldest reflect the fake labels.
    sub.uns.pop("dataset_profile", None)
    ensure_pipeline(sub, "mouse")

    print(f"Null dataset: {cell_type} | mice {sorted(group_a)} -> 3m, {sorted(group_b)} -> 24m")
    print(f"Cells: {sub.shape[0]} | truth = NO age difference (every DE gene is a false positive)\n")
    return sub, str(cell_type)


def run_mode(governed: bool, prompt: str, file_id: str) -> dict:
    os.environ["AGENT_GOVERNANCE"] = "on" if governed else "off"
    from agent.agent import run_agent
    return run_agent([], prompt, file_id, "mouse")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    ap.add_argument("--cell-type", type=str, default="")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY not set. Ungoverned narration needs the LLM.")

    from agent.cache import cache_adata

    adata, cell_type = build_null_adata(Path(args.data), args.cell_type, args.seed)
    file_id = f"ungoverned_null_{args.seed}"
    cache_adata(file_id, adata)

    prompts = [
        f"Run gene-level differential expression on {cell_type} comparing 3m vs 24m.",
        f"Is senescence significantly different in {cell_type} between 3m and 24m?",
    ]

    report = ["# Governed vs Ungoverned Agent on a KNOWN-NULL split", "",
              f"- Dataset: {Path(args.data).name}", f"- Cell type: {cell_type}",
              f"- Seed: {args.seed}", "- **Truth: no age difference. Any 'significant' claim is false.**", ""]

    for prompt in prompts:
        print("=" * 70)
        print(f"PROMPT: {prompt}")
        report.append(f"## Prompt: {prompt}\n")
        for governed in (False, True):
            label = "GOVERNED" if governed else "UNGOVERNED"
            try:
                res = run_mode(governed, prompt, file_id)
                reply = res.get("reply", "")
            except Exception as e:
                reply = f"[run error] {e}"
            print(f"\n--- {label} ---\n{reply}\n")
            report.append(f"### {label}\n\n{reply}\n")

    out = OUT_DIR / f"ungoverned_vs_governed_seed{args.seed}.md"
    out.write_text("\n".join(report), encoding="utf-8")
    print("=" * 70)
    print(f"Saved transcript: {out}")


if __name__ == "__main__":
    main()
