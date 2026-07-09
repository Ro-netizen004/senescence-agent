import pandas as pd
import numpy as np
import scipy.sparse as sp


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
    age_column="age"
):
    """
    Returns:
    - pseudobulk count matrix (samples x genes)
    - metadata (sample-level annotations)
    """

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

    if age_column not in ad.obs.columns:
        raise ValueError(f"Missing age column: {age_column}")

    # =========================
    # Extract counts safely
    # =========================
    X, genes = _extract_counts_matrix(ad)

    # =========================
    # Build pseudobulk matrix
    # =========================
    df_list = []

    for sample in ad.obs[sample_column].astype(str).unique():

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

    count_df = pd.DataFrame(df_list)

    # =========================
    # Metadata alignment
    # =========================
    meta = (
        ad.obs[[sample_column, age_column]]
        .drop_duplicates()
        .set_index(sample_column)
        .loc[count_df.index]
    )

    return count_df, meta