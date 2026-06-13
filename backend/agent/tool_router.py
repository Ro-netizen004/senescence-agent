
from tools.build_pseudobulk import build_pseudobulk_matrix
from tools.run_deseq2 import run_deseq2_pseudobulk


def run_deseq2_wrapper(
    adata,
    cell_type,
    sample_column="sample_id",
    age_column="age",
    reference_age=None,
    comparison_age=None,
):
    """
    Full pipeline:
    1. Build pseudobulk matrix
    2. Run DESeq2
    3. Return JSON-safe output
    """

    # =========================
    # Step 1: pseudobulk
    # =========================
    count_df, meta_df = build_pseudobulk_matrix(
        adata,
        cell_type,
        sample_column=sample_column,
        age_column=age_column
    )

    # =========================
    # Step 2: DESeq2
    # =========================
    results = run_deseq2_pseudobulk(
        count_df,
        meta_df,
        reference_age=reference_age,
        comparison_age=comparison_age,
    )

    # =========================
    # Step 3: JSON serialization (IMPORTANT)
    # =========================
    df = results["results"] if isinstance(results, dict) else results

    df = (
        df.head(100)
        .reset_index()
        .rename(columns={"index": "gene"})
    )

    output = {"results": df.to_dict(orient="records")}

    youngest = oldest = None
    if isinstance(results, dict):
        youngest = results.get("youngest_group")
        oldest = results.get("oldest_group")
        output["youngest_group"] = youngest
        output["oldest_group"] = oldest

    # Report only the samples actually used in the contrast. DESeq2 filters to
    # the two contrast ages internally, so counting the full pseudobulk matrix
    # (which may include other age groups, e.g. 18m) would misreport sample
    # counts and skew the downstream low-power assessment.
    contrast_meta = meta_df
    if "age" in meta_df.columns and youngest is not None and oldest is not None:
        contrast_meta = meta_df[
            meta_df["age"].astype(str).isin([str(youngest), str(oldest)])
        ]

    output["n_samples"] = int(contrast_meta.shape[0])
    if "age" in contrast_meta.columns:
        output["samples_per_age"] = (
            contrast_meta["age"].astype(str).value_counts().sort_index().to_dict()
        )

    return output

def build_tool_map(adata, species, tools):
    return {
        "generate_umap": lambda args: tools["generate_umap"](adata),

        "find_senescence_markers": lambda args: tools["find_senescence_markers"](adata, species),

        "senescence_score": lambda args: tools["senescence_score"](adata, species),

        "get_cluster_annotations": lambda args: tools["get_cluster_annotations"](adata),

        # =========================
        # DESEQ2 (NEW WRAPPER)
        # =========================
        "run_deseq2": lambda args: run_deseq2_wrapper(
            adata,
            args.get("cell_type"),
            args.get("sample_column", "sample_id"),
            args.get("age_column", "age"),
            args.get("reference_age"),
            args.get("comparison_age")
        ),

        # =========================
        # AGE ANALYSIS
        # =========================
        "compare_across_age": lambda args: tools["compare_across_age"](
            adata,
            args.get("age_column", "age"),
            args.get("cell_type_column", "cell_ontology_class"),
            species,
            cell_type=args.get("cell_type"),
            reference_age=args.get("reference_age"),
            comparison_age=args.get("comparison_age"),
        ),

        "test_senescence_difference": lambda args: tools["test_senescence_difference"](
            adata,
            args.get("cell_type"),
            args.get("age_column", "age"),
            args.get("cell_type_column", "cell_ontology_class"),
            args.get("sample_column", "sample_id"),
            args.get("reference_age") or "3m",
            args.get("comparison_age") or "24m",
            species,
        ),
    }
