
import os

from tools.build_pseudobulk import build_pseudobulk_matrix
from tools.run_deseq2 import run_deseq2_pseudobulk
from agent.admissibility import check_admissibility, admissibility_block_result
from agent.governance import governance_enabled


def run_deseq2_wrapper(
    adata,
    cell_type,
    sample_column="sample_id",
    group_column="age",
    reference_group=None,
    comparison_group=None,
    covariates=None,
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
        covariates=covariates,
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
        covariates=covariates,
    )

    # =========================
    # Step 3: JSON serialization (IMPORTANT)
    # =========================
    df = results["results"] if isinstance(results, dict) else results
    ref = results.get("reference_group") if isinstance(results, dict) else None
    comp = results.get("comparison_group") if isinstance(results, dict) else None
    if isinstance(results, dict):
        group_column = results.get("group_column", group_column)

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

    replicate_stability = None
    try:
        from tools.run_deseq2 import assess_replicate_stability
        replicate_stability = assess_replicate_stability(
            count_df, meta_df, df, group_column, ref, comp
        )
    except Exception as e:
        replicate_stability = {
            "verdict": "assessment_failed",
            "reason": str(e),
        }
        print(f"replicate stability assessment failed: {e}")

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

    output = {
        "results": df.to_dict(orient="records"),
        "governance_mode": "ungoverned_ablation" if not governance_enabled() else "governed",
        "method": "pseudobulk_deseq2",
        "statistical_unit": "biological_sample",
    }
    if os.getenv("AGENT_EVAL_DIAGNOSTICS", "").lower() in {"1", "true", "on"}:
        import numpy as np

        full_df = results["results"] if isinstance(results, dict) else results
        sig_index = full_df.index[full_df["padj"].fillna(1.0) < 0.05]
        diagnostic_counts = count_df.loc[:, count_df.columns.intersection(sig_index)]
        library_sizes = count_df.sum(axis=1).astype(float)
        detected_genes = (count_df > 0).sum(axis=1)

        # PCA-distance is a transparent influence screen, not a replacement for
        # DESeq2 Cook's distances. It identifies pseudobulk profiles far from the
        # donor centroid after log-CPM normalization.
        log_cpm = np.log1p(count_df.div(library_sizes.replace(0, np.nan), axis=0) * 1e6).fillna(0.0)
        centered = log_cpm.to_numpy(dtype=float)
        centered -= centered.mean(axis=0, keepdims=True)
        if centered.shape[0] > 1 and centered.shape[1] > 0:
            u, singular, _ = np.linalg.svd(centered, full_matrices=False)
            dimensions = min(3, len(singular))
            scores = u[:, :dimensions] * singular[:dimensions]
            pca_distance = np.sqrt((scores ** 2).sum(axis=1))
        else:
            pca_distance = np.zeros(centered.shape[0])

        sample_cells = meta_df.attrs.get("sample_cell_counts") or {}
        donor_rows = []
        for position, sample in enumerate(count_df.index):
            donor_rows.append({
                "sample_id": str(sample),
                "group": str(meta_df.loc[sample, group_column]),
                "library_size": int(library_sizes.loc[sample]),
                "detected_genes": int(detected_genes.loc[sample]),
                "n_cells": int(sample_cells.get(str(sample), 0)),
                "pca_distance": round(float(pca_distance[position]), 6),
            })

        prevalence = []
        for gene in sig_index:
            if gene not in diagnostic_counts.columns:
                continue
            expressed = diagnostic_counts[gene] > 0
            row = {
                "gene": str(gene),
                "n_donors_expressed": int(expressed.sum()),
            }
            for label in (ref, comp):
                group_samples = meta_df.index[meta_df[group_column].astype(str) == str(label)]
                row[f"n_expressed_{label}"] = int(expressed.reindex(group_samples, fill_value=False).sum())
            prevalence.append(row)

        output["evaluation_diagnostics"] = {
            "significant_genes": [str(gene) for gene in sig_index],
            "significant_gene_prevalence": prevalence,
            "donor_pseudobulk": donor_rows,
            "influence_metric": "PCA distance on log1p CPM pseudobulk profiles",
        }
    if n_significant is not None:
        output["n_significant_fdr_0_05"] = n_significant
    if result_plausibility is not None:
        output["result_plausibility"] = result_plausibility
    if replicate_stability is not None:
        output["replicate_stability"] = replicate_stability
    if volcano_path:
        output["plot_path"] = volcano_path
    if download_url:
        output["download_url"] = download_url

    if isinstance(results, dict):
        output["group_column"] = group_column
        output["reference_group"] = ref
        output["comparison_group"] = comp
        output["design_factors"] = results.get("design_factors", [group_column])
        output["covariates_used"] = results.get("covariates_used", [])
        output["covariates_dropped"] = results.get("covariates_dropped", [])
        output["count_validation"] = meta_df.attrs.get("count_validation")
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

    Both arms use the same inferential implementations. In the ungoverned
    ablation only the admissibility gate is removed; method parity is required
    so differences can be attributed to the governance stack.
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

    from agent.contrast import resolve_contrast

    def _deseq2_impl(args):
        spec = resolve_contrast(adata, args)
        if os.getenv("AGENT_EVAL_LOCK_ANALYSIS_SPEC", "").strip().lower() in {
            "1", "true", "on", "yes"
        }:
            # Same-method evaluation pre-registers the design from the dataset
            # profile. Neither deterministic nor LLM routing may change it.
            covariates = [
                value.strip()
                for value in os.getenv("AGENT_EVAL_COVARIATES", "").split(",")
                if value.strip()
            ]
        else:
            covariates = (
                args.get("covariates") if "covariates" in args
                else profile.get("deseq2_covariates") or []
            )
        return run_deseq2_wrapper(
            adata,
            spec.cell_type or args.get("cell_type"),
            spec.sample_column or sample_col,
            spec.group_column,
            spec.reference_group,
            spec.comparison_group,
            covariates,
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
