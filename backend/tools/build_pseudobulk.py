import pandas as pd
import numpy as np
import scipy.sparse as sp


# A sample needs at least this many cells of the queried cell type to count as a
# usable pseudobulk replicate. Aggregating 1-3 cells into a "replicate" yields an
# unrepresentative, library-size-skewed profile that produces spurious DESeq2
# fold-changes (the technical-artifact failure mode). This threshold is the SINGLE
# SOURCE OF TRUTH shared with the null harness (eval/ablation/null_harness), which
# gates on the identical value — so production admissibility matches the harness.
MIN_CELLS_PER_SAMPLE = 20


_SAMPLE_COLUMN_CANDIDATES = [
    "sample_id", "donor_id", "patient_id", "subject_id",
    "mouse.id", "mouse_id", "donor", "participant_id", "individual", "batch",
]


def _get_sample_column(adata, sample_column):
    """Auto-detect sample column, checking profile then a broad candidate list."""
    # Honour explicit column if present
    if sample_column and sample_column in adata.obs.columns:
        return sample_column

    # Use profile if available (set by pipeline)
    profile_col = (adata.uns.get("dataset_profile") or {}).get("sample_column")
    if profile_col and profile_col in adata.obs.columns:
        return profile_col

    # Broad fallback scan
    for candidate in _SAMPLE_COLUMN_CANDIDATES:
        if candidate in adata.obs.columns:
            return candidate

    raise ValueError(
        f"No sample/donor column found. Tried: {_SAMPLE_COLUMN_CANDIDATES}. "
        f"Available columns: {list(adata.obs.columns)}"
    )


def validate_count_matrix(X, source: str) -> dict:
    """Verify that a matrix is suitable for count-based DESeq2 inference."""
    values = X.data if sp.issparse(X) else np.asarray(X).ravel()
    if values.size == 0:
        return {"valid": False, "source": source, "reason": "count matrix is empty"}
    if not np.isfinite(values).all():
        return {"valid": False, "source": source, "reason": "counts contain NaN or infinity"}
    if np.min(values) < 0:
        return {"valid": False, "source": source, "reason": "counts contain negative values"}
    max_fractional_error = float(np.max(np.abs(values - np.rint(values))))
    if max_fractional_error > 1e-6:
        return {
            "valid": False,
            "source": source,
            "reason": "matrix contains non-integer values and appears normalized or transformed",
            "max_fractional_error": max_fractional_error,
        }
    return {
        "valid": True,
        "source": source,
        "n_nonzero": int(np.count_nonzero(values)),
        "max_count": float(np.max(values)),
    }


def _extract_counts_matrix(adata):
    """Return verified raw counts. Never fall back to normalized ``adata.X``."""
    candidates = []
    if "counts" in adata.layers:
        candidates.append((adata.layers["counts"], adata.var_names, "layers[counts]"))
    if adata.raw is not None:
        candidates.append((adata.raw.X, adata.raw.var_names, "raw.X"))

    failures = []
    for X, genes, source in candidates:
        check = validate_count_matrix(X, source)
        if check["valid"]:
            return X, genes, check
        failures.append(check)

    detail = "; ".join(f"{f['source']}: {f['reason']}" for f in failures)
    if not detail:
        detail = "neither layers['counts'] nor adata.raw.X is available"
    raise ValueError(
        "DESeq2 requires verified raw nonnegative integer counts; " + detail
    )


def build_pseudobulk_matrix(
    adata,
    cell_type,
    sample_column="sample_id",
    group_column="age",
    age_column=None,
    covariates=None,
):
    """
    Aggregate cells of one cell type into per-sample pseudobulk counts, carrying
    a single grouping column (age, condition, treatment, genotype, ...) as
    sample-level metadata.

    ``age_column`` is a deprecated alias for ``group_column`` (back-compat).

    Returns:
    - pseudobulk count matrix (samples x genes)
    - metadata (sample-level annotations, indexed by sample)
    """

    group_column = age_column or group_column

    # =========================
    # Filter cell type
    # =========================
    ct_col = (adata.uns.get("dataset_profile") or {}).get("cell_type_column") or "cell_ontology_class"
    ad = adata[
        adata.obs[ct_col].astype(str) == str(cell_type)
    ].copy()

    # =========================
    # Resolve columns
    # =========================
    sample_column = _get_sample_column(ad, sample_column)

    if group_column not in ad.obs.columns:
        raise ValueError(
            f"Missing grouping column: '{group_column}'. "
            f"Available columns: {list(ad.obs.columns)}"
        )

    # =========================
    # Extract counts safely
    # =========================
    X, genes, count_validation = _extract_counts_matrix(ad)

    # =========================
    # Drop samples with too few cells of this cell type
    # =========================
    # A handful of cells is not a reliable pseudobulk replicate: its profile is
    # dominated by a few cells and its library size is unrepresentative, which is
    # what drives spurious DESeq2 fold-changes. Excluded here so the tool operates
    # on exactly the replicates the admissibility gate counts (no gate/tool drift).
    sample_sizes = ad.obs[sample_column].astype(str).value_counts()
    usable_samples = set(sample_sizes[sample_sizes >= MIN_CELLS_PER_SAMPLE].index)

    # =========================
    # Build pseudobulk matrix
    # =========================
    df_list = []

    for sample in ad.obs[sample_column].astype(str).unique():

        if sample not in usable_samples:
            continue

        sub = ad[ad.obs[sample_column].astype(str) == sample]

        idx = sub.obs.index

        # subset rows in matrix
        if sp.issparse(X):
            sub_counts = X[ad.obs_names.get_indexer(idx), :]
            bulk = np.asarray(sub_counts.sum(axis=0)).flatten()
        else:
            sub_counts = X[ad.obs_names.get_indexer(idx), :]
            bulk = sub_counts.sum(axis=0)

        # Counts were validated before aggregation. Never coerce normalized
        # values to integers, which would create invalid DESeq2 input.
        bulk = np.rint(np.asarray(bulk)).astype(np.int64)

        df_list.append(pd.Series(bulk, index=genes, name=str(sample)))

    if not df_list:
        # Every sample was below the min-cell threshold. The admissibility gate
        # blocks this contrast up front in the governed path; return empty frames
        # so a direct caller fails cleanly rather than on a malformed matrix.
        return pd.DataFrame(columns=list(genes)), pd.DataFrame(columns=[group_column])

    count_df = pd.DataFrame(df_list)

    # =========================
    # Metadata alignment
    # =========================
    covariates = list(dict.fromkeys(covariates or []))
    metadata_columns = [group_column] + covariates
    missing = [c for c in metadata_columns if c not in ad.obs.columns]
    if missing:
        raise ValueError(f"Requested sample covariate column(s) not found: {missing}")

    sample_meta = ad.obs[[sample_column] + metadata_columns].copy()
    inconsistent = []
    for col in metadata_columns:
        per_sample_levels = sample_meta.groupby(sample_column, observed=True)[col].nunique(dropna=False)
        if not per_sample_levels.empty and per_sample_levels.max() > 1:
            inconsistent.append(col)
    if inconsistent:
        raise ValueError(
            f"Covariate/group columns vary within biological samples: {inconsistent}. "
            "DESeq2 metadata must have one value per sample."
        )

    meta = sample_meta.drop_duplicates(subset=[sample_column]).set_index(sample_column).loc[count_df.index]
    meta.attrs["count_validation"] = count_validation
    meta.attrs["sample_cell_counts"] = {
        str(sample): int(sample_sizes.get(str(sample), 0)) for sample in count_df.index
    }
    return count_df, meta
