
from tools.build_pseudobulk import build_pseudobulk_matrix
from tools.run_deseq2 import run_deseq2_pseudobulk
from agent.admissibility import check_admissibility, admissibility_block_result


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

def build_tool_map(adata, species, tools, governed: bool = True):
    """Build the name->callable tool map.

    When ``governed`` is False (ablation only), the admissibility gate is
    removed and the two inferential tools are swapped for per-cell
    (pseudoreplicating) implementations. Production always passes governed=True.
    """
    profile = adata.uns.get("dataset_profile") or {}
    age_col = profile.get("age_column") or "age"
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    sample_col = profile.get("sample_column") or "sample_id"
    youngest = profile.get("youngest") or "3m"
    oldest = profile.get("oldest") or "24m"

    def _gate(tool_name, fn):
        """Gate 1: admissibility pre-check runs BEFORE the tool. If the inference
        is inadmissible given the data design, the tool never runs and a BLOCKED
        result is returned. Admissible-but-imperfect contrasts pass with warnings.

        In ungoverned mode this gate is a no-op (the tool always runs)."""
        if not governed:
            return fn
        def gated(args):
            adm = check_admissibility(tool_name, args or {}, adata)
            if not adm["admissible"]:
                return admissibility_block_result(tool_name, adm)
            result = fn(args)
            if isinstance(result, dict) and adm.get("warnings"):
                result.setdefault("admissibility_warnings", []).extend(adm["warnings"])
            return result
        return gated

    if governed:
        def _deseq2_impl(args):
            return run_deseq2_wrapper(
                adata,
                args.get("cell_type"),
                args.get("sample_column", sample_col),
                args.get("age_column", age_col),
                args.get("reference_age") or youngest,
                args.get("comparison_age") or oldest,
            )

        def _test_impl(args):
            return tools["test_senescence_difference"](
                adata,
                args.get("cell_type"),
                args.get("age_column", age_col),
                args.get("cell_type_column", ct_col),
                args.get("sample_column", sample_col),
                args.get("reference_age") or youngest,
                args.get("comparison_age") or oldest,
                species,
            )
    else:
        # Ungoverned ablation: per-cell (pseudoreplicating) versions.
        from tools.percell_inference import (
            differential_expression_percell,
            test_senescence_difference_percell,
        )

        def _deseq2_impl(args):
            return differential_expression_percell(
                adata,
                args.get("cell_type"),
                args.get("age_column", age_col),
                args.get("cell_type_column", ct_col),
                args.get("sample_column", sample_col),
                args.get("reference_age") or youngest,
                args.get("comparison_age") or oldest,
                species,
            )

        def _test_impl(args):
            return test_senescence_difference_percell(
                adata,
                args.get("cell_type"),
                args.get("age_column", age_col),
                args.get("cell_type_column", ct_col),
                args.get("sample_column", sample_col),
                args.get("reference_age") or youngest,
                args.get("comparison_age") or oldest,
                species,
            )

    return {
        "generate_umap": lambda args: tools["generate_umap"](adata),

        "find_senescence_markers": lambda args: tools["find_senescence_markers"](adata, species),

        "senescence_score": lambda args: tools["senescence_score"](adata, species),

        "get_cluster_annotations": lambda args: tools["get_cluster_annotations"](adata),

        "run_deseq2": _gate("run_deseq2", _deseq2_impl),

        "compare_across_age": lambda args: tools["compare_across_age"](
            adata,
            args.get("age_column", age_col),
            args.get("cell_type_column", ct_col),
            species,
            cell_type=args.get("cell_type"),
            reference_age=args.get("reference_age"),
            comparison_age=args.get("comparison_age"),
        ),

        "test_senescence_difference": _gate("test_senescence_difference", _test_impl),
    }
