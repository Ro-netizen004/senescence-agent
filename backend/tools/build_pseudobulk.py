import pandas as pd
import numpy as np
import scipy.sparse as sp


def _get_sample_column(adata, sample_column):
    """
    Auto-detect sample column with fallback.
    """
    if sample_column in adata.obs.columns:
        return sample_column

    if "mouse.id" in adata.obs.columns:
        return "mouse.id"

    if "mouse_id" in adata.obs.columns:
        return "mouse_id"

    raise ValueError("No valid sample column found (sample_id / mouse_id / mouse.id)")


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
    ad = adata[
        adata.obs["cell_ontology_class"].astype(str) == str(cell_type)
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
            sub_counts = X[sub.obs_names.get_indexer(idx), :]
            bulk = np.asarray(sub_counts.sum(axis=0)).flatten()
        else:
            sub_counts = X[sub.obs_names.get_indexer(idx), :]
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