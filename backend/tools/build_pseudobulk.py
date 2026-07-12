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


def _extract_counts_matrix(adata):
    """
    Robust extraction priority:
    1. adata.layers['counts']
    2. adata.raw.X
    3. adata.X
    """

    if "counts" in adata.layers:
        X = adata.layers["counts"]
        genes = adata.var_names
        return X, genes

    if adata.raw is not None:
        X = adata.raw.X
        genes = adata.raw.var_names
        return X, genes

    X = adata.X
    genes = adata.var_names
    return X, genes


def build_pseudobulk_matrix(
    adata,
    cell_type,
    sample_column="sample_id",
    group_column="age",
    age_column=None,
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
    X, genes = _extract_counts_matrix(ad)

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

        # IMPORTANT: integer counts for DESeq2
        bulk = np.asarray(bulk).astype(int)

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
    meta = (
        ad.obs[[sample_column, group_column]]
        .drop_duplicates()
        .set_index(sample_column)
        .loc[count_df.index]
    )

    return count_df, meta