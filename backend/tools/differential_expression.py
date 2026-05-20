import scanpy as sc

def differential_expression(adata, groupby="leiden", n_top=10):

    # Safety check (prevents your earlier bug)
    if "X_pca" not in adata.obsm:
        raise ValueError("Run PCA + neighbors before DE analysis")

    sc.tl.rank_genes_groups(
        adata,
        groupby=groupby,
        method="wilcoxon"
    )

    groups = adata.obs[groupby].unique().tolist()

    top_markers = {}

    for g in groups:
        df = sc.get.rank_genes_groups_df(adata, group=g)
        top_markers[g] = df.head(n_top).to_dict(orient="records")

    return {
        "top_markers": top_markers,
        "groups": groups
    }