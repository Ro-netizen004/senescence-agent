"""Deterministic validity-gate challenge suite.

Synthesizes minimal AnnData objects that exercise each admissibility gate,
runs check_admissibility, and scores sensitivity/specificity.

No LLM calls. CPU-only. Deterministic.

Usage:
  python eval/ablation/gate_challenge/run_gate_challenge.py \
      --output-dir eval/results/gate_challenge

Challenges:
  1. Valid balanced design             -> admissible (allow)
  2. Too few replicates (score test)   -> blocked
  3. Too few replicates (DESeq2)       -> blocked
  4. Perfect group-sex confounding     -> blocked
  5. Perfect group-batch confounding   -> blocked
  6. Partial confounding               -> admissible + warning
  7. No sample column (pseudorep)      -> blocked
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from agent.admissibility import check_admissibility  # noqa: E402


def _make_adata(n_samples, n_cells_per_sample, n_genes, group_labels,
                sample_col="mouse_id", group_col="group",
                extra_cols=None, remove_sample_col=False):
    """Build a minimal AnnData with the given design."""
    import anndata
    import scipy.sparse as sp

    obs_rows = []
    for i, g in enumerate(group_labels):
        for j in range(n_cells_per_sample):
            row = {
                group_col: g,
                "cell_type": "TestCell",
            }
            if not remove_sample_col:
                row[sample_col] = f"sample_{i}"
            if extra_cols:
                for col_name, col_vals in extra_cols.items():
                    row[col_name] = col_vals[i]
            obs_rows.append(row)

    obs = pd.DataFrame(obs_rows)
    X = sp.random(len(obs), n_genes, density=0.3, format="csr", dtype=np.float32)
    X.data = np.abs(X.data) * 100
    adata = anndata.AnnData(X=X, obs=obs)
    adata.var_names = [f"gene_{i}" for i in range(n_genes)]

    profile = {"sample_column": sample_col if not remove_sample_col else None}
    adata.uns["dataset_profile"] = profile
    return adata


CHALLENGES = []


def challenge(name, expect_admissible, expect_warning=None, tool="run_deseq2"):
    def decorator(fn):
        CHALLENGES.append({
            "name": name,
            "fn": fn,
            "expect_admissible": expect_admissible,
            "expect_warning": expect_warning,
            "tool": tool,
        })
        return fn
    return decorator


@challenge("valid_balanced_4v4", expect_admissible=True)
def _valid_balanced(seed):
    groups = ["ctrl"] * 4 + ["treat"] * 4
    adata = _make_adata(8, 50, 100, groups)
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


@challenge("valid_balanced_6v6", expect_admissible=True)
def _valid_balanced_large(seed):
    groups = ["ctrl"] * 6 + ["treat"] * 6
    adata = _make_adata(12, 50, 100, groups)
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


@challenge("too_few_replicates_score_test", expect_admissible=False,
           tool="test_senescence_difference")
def _too_few_score(seed):
    groups = ["ctrl", "treat"]
    adata = _make_adata(2, 50, 100, groups)
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


@challenge("too_few_replicates_deseq2", expect_admissible=False)
def _too_few_deseq2(seed):
    groups = ["ctrl", "ctrl", "treat", "treat"]
    adata = _make_adata(4, 50, 100, groups)
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


@challenge("perfect_group_sex_confound", expect_admissible=False)
def _sex_confound(seed):
    groups = ["ctrl"] * 3 + ["treat"] * 3
    sexes = ["M", "M", "M", "F", "F", "F"]
    adata = _make_adata(6, 50, 100, groups, extra_cols={"sex": sexes})
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


@challenge("perfect_group_batch_confound", expect_admissible=False)
def _batch_confound(seed):
    groups = ["ctrl"] * 3 + ["treat"] * 3
    batches = ["batch1", "batch1", "batch1", "batch2", "batch2", "batch2"]
    adata = _make_adata(6, 50, 100, groups, extra_cols={"pool": batches})
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


@challenge("partial_confound", expect_admissible=True, expect_warning="partial_confounding")
def _partial_confound(seed):
    groups = ["ctrl"] * 4 + ["treat"] * 4
    sexes = ["M", "M", "F", "M", "F", "F", "F", "M"]
    adata = _make_adata(8, 50, 100, groups, extra_cols={"sex": sexes})
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


@challenge("no_sample_column_pseudorep", expect_admissible=False)
def _no_sample_col(seed):
    groups = ["ctrl"] * 4 + ["treat"] * 4
    adata = _make_adata(8, 50, 100, groups, remove_sample_col=True)
    adata.uns["dataset_profile"] = {}
    args = {"cell_type": "TestCell", "reference_group": "ctrl",
            "comparison_group": "treat", "group_column": "group"}
    return adata, args


def run_all(n_seeds=30, output_dir=None):
    results = []
    for ch in CHALLENGES:
        print(f"\n{'='*60}")
        print(f"Challenge: {ch['name']}")
        print(f"  Expected admissible: {ch['expect_admissible']}")
        correct = 0
        warning_correct = 0
        records = []

        for seed in range(n_seeds):
            adata, args = ch["fn"](seed)
            result = check_admissibility(ch["tool"], args, adata)
            got_admissible = result["admissible"]
            match = got_admissible == ch["expect_admissible"]
            if match:
                correct += 1

            warning_match = True
            if ch["expect_warning"]:
                warning_match = any(
                    ch["expect_warning"] in w for w in result.get("warnings", [])
                )
                if warning_match:
                    warning_correct += 1

            records.append({
                "seed": seed,
                "admissible": got_admissible,
                "expected": ch["expect_admissible"],
                "correct": match,
                "blocked_reasons": result.get("blocked_reasons", []),
                "warnings": result.get("warnings", []),
            })

        accuracy = correct / n_seeds
        print(f"  Accuracy: {correct}/{n_seeds} ({accuracy:.1%})")
        if ch["expect_warning"]:
            print(f"  Warning detection: {warning_correct}/{n_seeds}")

        summary = {
            "challenge": ch["name"],
            "tool": ch["tool"],
            "expect_admissible": ch["expect_admissible"],
            "expect_warning": ch["expect_warning"],
            "n_seeds": n_seeds,
            "correct": correct,
            "accuracy": accuracy,
            "details": records,
        }
        if ch["expect_warning"]:
            summary["warning_detection_rate"] = warning_correct / n_seeds
        results.append(summary)

    n_challenges = len(CHALLENGES)
    n_block = sum(1 for c in CHALLENGES if not c["expect_admissible"])
    n_allow = sum(1 for c in CHALLENGES if c["expect_admissible"])

    block_correct = sum(
        r["correct"] for r, c in zip(results, CHALLENGES) if not c["expect_admissible"]
    )
    allow_correct = sum(
        r["correct"] for r, c in zip(results, CHALLENGES) if c["expect_admissible"]
    )

    sensitivity = block_correct / (n_block * n_seeds) if n_block else 0
    specificity = allow_correct / (n_allow * n_seeds) if n_allow else 0

    print(f"\n{'='*60}")
    print(f"SUMMARY: {n_challenges} challenges x {n_seeds} seeds")
    print(f"  Sensitivity (block when should block): {sensitivity:.1%}")
    print(f"  Specificity (allow when should allow): {specificity:.1%}")

    report = {
        "n_challenges": n_challenges,
        "n_seeds": n_seeds,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "per_challenge": [{k: v for k, v in r.items() if k != "details"} for r in results],
    }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "gate_challenge_summary.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        (output_dir / "gate_challenge_full.json").write_text(
            json.dumps(results, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nSaved to {output_dir}")

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "eval" / "results" / "gate_challenge")
    parser.add_argument("--n-seeds", type=int, default=30)
    args = parser.parse_args()
    report = run_all(n_seeds=args.n_seeds, output_dir=args.output_dir)
    all_perfect = all(
        r["accuracy"] == 1.0 for r in report["per_challenge"]
    )
    raise SystemExit(0 if all_perfect else 1)


if __name__ == "__main__":
    main()
