"""Memory-safe OneK1K donor pseudobulk construction and null allocation."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import scipy.sparse as sp

MIN_CELLS_PER_DONOR = 20


def _allocation_id(group_a: list[str], group_b: list[str]) -> str:
    sides = sorted(("|".join(sorted(group_a)), "|".join(sorted(group_b))))
    return hashlib.sha256("::".join(sides).encode()).hexdigest()


def paired_null_allocation(metadata: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, dict]:
    """Pair donors within pool/sex by adjacent age, then randomize pair orientation."""
    required = {"individual", "pool", "sex", "age"}
    missing = sorted(required - set(metadata.columns))
    if missing:
        raise ValueError(f"Missing allocation metadata: {missing}")

    rng = np.random.default_rng(seed)
    assigned: dict[str, str] = {}
    excluded: list[str] = []
    pair_records = []
    strata = defaultdict(list)
    for row in metadata.itertuples(index=False):
        strata[(str(row.pool), str(row.sex))].append((float(row.age), str(row.individual)))

    for stratum, donors in sorted(strata.items()):
        donors.sort()
        if len(donors) % 2:
            # Exclude the donor whose removal yields the smallest total adjacent
            # age mismatch. Randomness is used only to break exact ties.
            costs = []
            for candidate in range(len(donors)):
                retained = donors[:candidate] + donors[candidate + 1 :]
                cost = sum(
                    abs(retained[i][0] - retained[i + 1][0])
                    for i in range(0, len(retained), 2)
                )
                costs.append(cost)
            best = np.flatnonzero(np.isclose(costs, min(costs)))
            excluded_index = int(rng.choice(best))
            excluded.append(donors.pop(excluded_index)[1])
        for index in range(0, len(donors), 2):
            left, right = donors[index], donors[index + 1]
            if bool(rng.integers(0, 2)):
                left, right = right, left
            assigned[left[1]] = "fake_A"
            assigned[right[1]] = "fake_B"
            pair_records.append({
                "pool": stratum[0], "sex": stratum[1],
                "fake_A": left[1], "fake_B": right[1],
                "age_difference": abs(left[0] - right[0]),
            })

    result = metadata[metadata["individual"].astype(str).isin(assigned)].copy()
    result["null_group"] = result["individual"].astype(str).map(assigned)
    group_a = result.loc[result["null_group"] == "fake_A", "individual"].astype(str).tolist()
    group_b = result.loc[result["null_group"] == "fake_B", "individual"].astype(str).tolist()
    if len(group_a) != len(group_b) or not group_a:
        raise RuntimeError("Paired allocator did not produce two nonempty equal groups")
    diagnostics = {
        "seed": seed,
        "allocation_id": _allocation_id(group_a, group_b),
        "n_per_group": len(group_a),
        "n_excluded_unpaired": len(excluded),
        "excluded_donors": sorted(excluded),
        "n_pairs": len(pair_records),
        "mean_within_pair_age_difference": round(
            float(np.mean([row["age_difference"] for row in pair_records])), 4
        ),
        "max_within_pair_age_difference": float(
            max(row["age_difference"] for row in pair_records)
        ),
        "pairs": pair_records,
    }
    return result.set_index("individual"), diagnostics


def build_onek1k_pseudobulk(
    data_path: Path,
    *,
    cell_label: str = "Mono C",
    min_cells_per_donor: int = MIN_CELLS_PER_DONOR,
    chunk_size: int = 2000,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Aggregate raw backed `X` counts by donor without copying the full AnnData."""
    adata = ad.read_h5ad(data_path, backed="r")
    required = {"individual", "cell_label", "pool", "sex", "age", "nCount_RNA"}
    missing = sorted(required - set(adata.obs.columns))
    if missing:
        raise ValueError(f"OneK1K metadata columns missing: {missing}")

    selected = adata.obs["cell_label"].astype(str).eq(cell_label)
    donor_counts = adata.obs.loc[selected, "individual"].astype(str).value_counts()
    eligible = sorted(donor_counts[donor_counts >= min_cells_per_donor].index)
    if len(eligible) < 20:
        raise ValueError(f"{cell_label} has only {len(eligible)} eligible donors")

    eligible_set = set(eligible)
    row_mask = selected & adata.obs["individual"].astype(str).isin(eligible_set)
    rows = np.flatnonzero(row_mask.to_numpy())
    donor_index = {donor: index for index, donor in enumerate(eligible)}
    accumulated = sp.csr_matrix((len(eligible), adata.n_vars), dtype=np.int64)

    for start in range(0, len(rows), chunk_size):
        chunk_rows = rows[start : start + chunk_size]
        matrix = adata.X[chunk_rows, :]
        if not sp.issparse(matrix):
            matrix = sp.csr_matrix(matrix)
        values = matrix.data
        if values.size and (
            not np.isfinite(values).all()
            or (values < 0).any()
            or not np.allclose(values, np.rint(values))
        ):
            raise ValueError("OneK1K X is not a raw nonnegative integer count matrix")
        local_donors = adata.obs.iloc[chunk_rows]["individual"].astype(str)
        targets = np.fromiter((donor_index[value] for value in local_donors), dtype=np.int64)
        selector = sp.csr_matrix(
            (np.ones(len(targets), dtype=np.int8), (targets, np.arange(len(targets)))),
            shape=(len(eligible), len(targets)),
        )
        accumulated += selector @ matrix.astype(np.int64)

    first = (
        adata.obs.loc[row_mask, ["individual", "pool", "sex", "age"]]
        .drop_duplicates("individual")
        .copy()
    )
    consistency = adata.obs.loc[row_mask].groupby("individual", observed=True)[
        ["pool", "sex", "age"]
    ].nunique(dropna=False)
    if (consistency > 1).any().any():
        raise ValueError("Pool, sex, or age varies within at least one donor")
    metadata = first.set_index(first["individual"].astype(str)).drop(columns="individual")
    metadata.index.name = "individual"
    metadata = metadata.loc[eligible]

    # DESeq2 ultimately requires a dense donor-by-gene table. Materializing only
    # after aggregation bounds this at roughly donors x genes, rather than
    # cells x genes (about 137 MB for Mono C at int64).
    count_df = pd.DataFrame(
        accumulated.toarray(), index=eligible, columns=adata.var_names.astype(str)
    )
    diagnostics = {
        "dataset": str(Path(data_path).resolve()),
        "cell_label": cell_label,
        "n_cells": int(len(rows)),
        "n_eligible_donors": len(eligible),
        "min_cells_per_donor": min_cells_per_donor,
        "cells_per_donor": {
            donor: int(donor_counts[donor]) for donor in eligible
        },
        "count_source": "X",
        "shape": [int(count_df.shape[0]), int(count_df.shape[1])],
    }
    return count_df, metadata, diagnostics
