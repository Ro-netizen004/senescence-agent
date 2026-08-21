"""Perform a no-LLM schema audit for a many-donor single-cell dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import anndata as ad
import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("--donor-column", required=True)
    parser.add_argument("--cell-type-column", required=True)
    parser.add_argument("--count-layer", default="counts")
    parser.add_argument("--min-cells-per-donor", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("onek1k_schema_audit.json"))
    args = parser.parse_args()

    adata = ad.read_h5ad(args.data, backed="r")
    for column in (args.donor_column, args.cell_type_column):
        if column not in adata.obs:
            raise SystemExit(f"Required observation column not found: {column}")
    if args.count_layer in adata.layers:
        count_source = f"layers[{args.count_layer!r}]"
        matrix = adata.layers[args.count_layer]
    else:
        count_source = "X"
        matrix = adata.X

    sample = matrix[: min(1000, adata.n_obs), : min(1000, adata.n_vars)]
    values = sample.data if hasattr(sample, "data") else np.asarray(sample).ravel()
    finite = values[np.isfinite(values)]
    integer_like = bool(np.allclose(finite, np.round(finite))) if finite.size else True
    nonnegative = bool((finite >= 0).all()) if finite.size else True

    donors = adata.obs[args.donor_column].astype(str)
    cell_types = adata.obs[args.cell_type_column].astype(str)
    counts = (
        adata.obs.assign(_donor=donors, _cell_type=cell_types)
        .groupby(["_cell_type", "_donor"], observed=True)
        .size()
    )
    eligible = counts[counts >= args.min_cells_per_donor]
    eligible_by_type = eligible.groupby(level=0).size().sort_values(ascending=False)
    report = {
        "status": "schema_audit_only_no_llm_calls",
        "dataset": str(args.data.resolve()),
        "shape": [int(adata.n_obs), int(adata.n_vars)],
        "donor_column": args.donor_column,
        "n_donors": int(donors.nunique()),
        "cell_type_column": args.cell_type_column,
        "n_cell_types": int(cell_types.nunique()),
        "count_source": count_source,
        "sampled_counts_integer_like": integer_like,
        "sampled_counts_nonnegative": nonnegative,
        "min_cells_per_donor": args.min_cells_per_donor,
        "top_cell_types_by_eligible_donors": {
            str(name): int(value) for name, value in eligible_by_type.head(30).items()
        },
        "metadata_columns": list(map(str, adata.obs.columns)),
        "ready_for_protocol_review": bool(
            integer_like and nonnegative and (eligible_by_type >= 20).any()
        ),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
