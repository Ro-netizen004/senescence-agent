
from tools.build_pseudobulk import build_pseudobulk_matrix
from tools.run_deseq2 import run_deseq2_pseudobulk
from agent.admissibility import check_admissibility, admissibility_block_result


def run_deseq2_wrapper(
    adata,
    cell_type,
    sample_column="sample_id",
    group_column="age",
    reference_group=None,
    comparison_group=None,
):
    """
    Full pipeline:
    1. Build pseudobulk matrix for one cell type, carrying `group_column`
    2. Run DESeq2 between `reference_group` and `comparison_group`
    3. Return JSON-safe output
    """

    # =========================
    # Step 1: pseudobulk
    # =========================
    count_df, meta_df = build_pseudobulk_matrix(
        adata,
        cell_type,
        sample_column=sample_column,
        group_column=group_column,
    )

    # =========================
    # Step 2: DESeq2
    # =========================
    results = run_deseq2_pseudobulk(
        count_df,
        meta_df,
        group_column=group_column,
        reference_group=reference_group,
        comparison_group=comparison_group,
    )

    # =========================
    # Step 3: JSON serialization (IMPORTANT)
    # =========================
    df = results["results"] if isinstance(results, dict) else results

    # True significant-gene count from the FULL results, before we truncate the
    # display list to the top 100 (otherwise the count is capped at 100).
    n_significant = int((df["padj"] < 0.05).sum()) if "padj" in df.columns else None

    # Gate 2: assess result plausibility on the FULL significant set (effect-size
    # magnitude + directional skew) — flags technical-artifact fingerprints.
    result_plausibility = None
    try:
        from tools.run_deseq2 import assess_de_plausibility
        result_plausibility = assess_de_plausibility(df)
    except Exception as e:
        print(f"plausibility assessment failed: {e}")

    # Volcano plot from the FULL results (rendered inline by the frontend).
    volcano_path = None
    try:
        from tools.run_deseq2 import generate_volcano
        from tools.config import OUTPUT_DIR
        yg = results.get("youngest_group") if isinstance(results, dict) else None
        og = results.get("oldest_group") if isinstance(results, dict) else None
        volcano_path = generate_volcano(df, OUTPUT_DIR, oldest=str(og or "comparison"),
                                        youngest=str(yg or "reference"))
    except Exception as e:  # never let a plot failure break the analysis
        print(f"volcano generation failed: {e}")

    # Save the FULL results as a downloadable CSV (all genes, not just top 100).
    download_url = None
    try:
        import os
        from tools.config import OUTPUT_DIR
        df.to_csv(os.path.join(OUTPUT_DIR, "deseq2_results.csv"))
        download_url = "/plots/deseq2_results.csv"
    except Exception as e:
        print(f"CSV export failed: {e}")

    df = (
        df.head(100)
        .reset_index()
        .rename(columns={"index": "gene"})
    )

    output = {"results": df.to_dict(orient="records")}
    if n_significant is not None:
        output["n_significant_fdr_0_05"] = n_significant
    if result_plausibility is not None:
        output["result_plausibility"] = result_plausibility
    if volcano_path:
        output["plot_path"] = volcano_path
    if download_url:
        output["download_url"] = download_url

    ref = comp = None
    if isinstance(results, dict):
        ref = results.get("reference_group")
        comp = results.get("comparison_group")
        group_column = results.get("group_column", group_column)
        output["group_column"] = group_column
        output["reference_group"] = ref
        output["comparison_group"] = comp
        # Legacy aliases (older renderers / eval expect these).
        output["youngest_group"] = ref
        output["oldest_group"] = comp

    # Report only the samples actually used in the contrast. DESeq2 filters to
    # the two contrast groups internally, so counting the full pseudobulk matrix
    # (which may include other groups, e.g. 18m) would misreport sample counts
    # and skew the downstream low-power assessment.
    contrast_meta = meta_df
    if group_column in meta_df.columns and ref is not None and comp is not None:
        contrast_meta = meta_df[
            meta_df[group_column].astype(str).isin([str(ref), str(comp)])
        ]

    output["n_samples"] = int(contrast_meta.shape[0])
    if group_column in contrast_meta.columns:
        counts = (
            contrast_meta[group_column].astype(str).value_counts().sort_index().to_dict()
        )
        output["samples_per_group"] = counts
        output["samples_per_age"] = counts  # legacy alias

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
    primary_group_col = profile.get("primary_group_column") or age_col

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
        from agent.contrast import resolve_contrast

        def _deseq2_impl(args):
            spec = resolve_contrast(adata, args)
            return run_deseq2_wrapper(
                adata,
                spec.cell_type or args.get("cell_type"),
                spec.sample_column or sample_col,
                spec.group_column,
                spec.reference_group,
                spec.comparison_group,
            )

        def _test_impl(args):
            spec = resolve_contrast(adata, args)
            return tools["test_senescence_difference"](
                adata,
                spec.cell_type or args.get("cell_type"),
                spec.group_column,
                spec.cell_type_column,
                spec.sample_column or sample_col,
                spec.reference_group,
                spec.comparison_group,
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
        "generate_umap": lambda args: tools["generate_umap"](adata, species=species),

        "find_senescence_markers": lambda args: tools["find_senescence_markers"](adata, species),

        "senescence_score": lambda args: tools["senescence_score"](adata, species),

        "get_cluster_annotations": lambda args: tools["get_cluster_annotations"](adata, species),

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
