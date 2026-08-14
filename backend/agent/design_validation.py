"""Deterministic validation for sample-level regression designs."""

from __future__ import annotations

import numpy as np
import pandas as pd


def validate_factor_design(meta, group_column: str, covariates=None) -> dict:
    """Validate completeness and full rank for a two-group DESeq2 design.

    Returns an audit record and raises ``ValueError`` for designs that cannot
    identify separate effects. Categorical factors use treatment coding;
    genuinely numeric covariates remain continuous.
    """
    covariates = list(dict.fromkeys(covariates or []))
    if group_column in covariates:
        raise ValueError(
            f"Grouping column '{group_column}' cannot also be an adjustment covariate"
        )
    factors = covariates + [group_column]
    missing_columns = [c for c in factors if c not in meta.columns]
    if missing_columns:
        raise ValueError(f"Design factor column(s) not found: {missing_columns}")

    missing_counts = {c: int(meta[c].isna().sum()) for c in factors if meta[c].isna().any()}
    if missing_counts:
        raise ValueError(f"Design factors contain missing sample values: {missing_counts}")

    encoded = []
    encoded_names = []
    for factor in factors:
        values = meta[factor]
        if values.nunique(dropna=True) < 2:
            if factor == group_column:
                raise ValueError(f"Grouping column '{group_column}' has fewer than two levels")
            continue
        if pd.api.types.is_numeric_dtype(values) and values.nunique() > 2:
            encoded.append(values.astype(float).to_numpy()[:, None])
            encoded_names.append(factor)
        else:
            dummies = pd.get_dummies(values.astype(str), prefix=factor, drop_first=True, dtype=float)
            encoded.append(dummies.to_numpy())
            encoded_names.extend(dummies.columns.astype(str).tolist())

    matrix = np.ones((len(meta), 1), dtype=float)
    if encoded:
        matrix = np.column_stack([matrix] + encoded)
    rank = int(np.linalg.matrix_rank(matrix))
    n_columns = int(matrix.shape[1])
    if rank < n_columns:
        raise ValueError(
            "Design matrix is not full rank; requested covariates are duplicate, "
            "perfectly collinear, or confounded with the contrast "
            f"(rank={rank}, columns={n_columns}, encoded={encoded_names})"
        )
    return {
        "n_samples": int(len(meta)),
        "rank": rank,
        "n_columns": n_columns,
        "full_rank": True,
        "factors": factors,
        "encoded_columns": ["intercept"] + encoded_names,
    }
