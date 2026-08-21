"""Run one no-LLM OneK1K donor-split pseudobulk DESeq2 smoke test."""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from tools.run_deseq2 import run_deseq2_pseudobulk  # noqa: E402

from build_pseudobulk import build_onek1k_pseudobulk, paired_null_allocation  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("--cell-label", default="Mono C")
    parser.add_argument("--seed", type=int, default=3000)
    parser.add_argument("--output-dir", type=Path, default=Path("D:/OneK1K/results/smoke_seed3000"))
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Do not write the complete gene-level DESeq2 table.",
    )
    args = parser.parse_args()

    count_df, donor_meta, build_diagnostics = build_onek1k_pseudobulk(
        args.data, cell_label=args.cell_label
    )
    allocated_meta, allocation = paired_null_allocation(
        donor_meta.reset_index(), args.seed
    )
    count_df = count_df.loc[allocated_meta.index]
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        result = run_deseq2_pseudobulk(
            count_df,
            allocated_meta,
            group_column="null_group",
            reference_group="fake_A",
            comparison_group="fake_B",
            covariates=["pool", "sex", "age"],
        )
    table = result.pop("results")
    significant = table[table["padj"].notna() & (table["padj"] < 0.05)]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.summary_only:
        table.to_csv(args.output_dir / "deseq2_results.csv")
    allocated_meta.to_csv(args.output_dir / "donor_allocation.csv")
    top = table.head(100).reset_index().rename(columns={"index": "gene"})
    top_records = json.loads(top.to_json(orient="records"))
    numerical_warnings = sorted({
        str(item.message) for item in caught_warnings
        if issubclass(item.category, RuntimeWarning)
    })
    finite = {
        column: int(np.isfinite(table[column].to_numpy(dtype=float)).sum())
        for column in ("baseMean", "log2FoldChange", "lfcSE", "stat", "pvalue", "padj")
        if column in table
    }
    numerical_health = {
        "runtime_warning_count": len(numerical_warnings),
        "runtime_warnings": numerical_warnings,
        "finite_values_by_column": finite,
        "nonfinite_values_by_column": {
            column: int(len(table) - count) for column, count in finite.items()
        },
        "all_test_statistics_finite": all(
            finite.get(column, len(table)) == len(table)
            for column in ("log2FoldChange", "lfcSE", "stat", "pvalue")
        ),
    }
    summary = {
        "status": "direct_statistical_smoke_no_llm_calls",
        "summary_only": args.summary_only,
        "build": build_diagnostics,
        "allocation": allocation,
        "deseq2": result,
        "n_genes_tested": int(len(table)),
        "n_null_discoveries_fdr_0_05": int(len(significant)),
        "numerical_health": numerical_health,
        "top_100_results": top_records,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "output": str(args.output_dir.resolve()),
        "donors_per_group": allocation["n_per_group"],
        "n_genes_tested": len(table),
        "n_null_discoveries_fdr_0_05": len(significant),
    }, indent=2))


if __name__ == "__main__":
    main()
