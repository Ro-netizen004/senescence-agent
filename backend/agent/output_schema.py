"""
Build strict output schema (facts + state slots). No prose generation.
"""

from __future__ import annotations

from typing import Any, Optional

from agent.inference_state import InferenceState, assign_inference_state


def _observation_numeric_higher(
    ref_label: str, ref_val: Optional[float], comp_label: str, comp_val: Optional[float]
) -> Optional[str]:
    if ref_val is None or comp_val is None:
        return None
    if comp_val > ref_val:
        return f"{comp_label} median ({comp_val}) > {ref_label} median ({ref_val})"
    if comp_val < ref_val:
        return f"{comp_label} median ({comp_val}) < {ref_label} median ({ref_val})"
    return f"{comp_label} median equals {ref_label} median ({ref_val})"


def _base_schema(tool_name: str, result: dict, args: dict) -> dict:
    state = assign_inference_state(tool_name, result)
    inf = result.get("inference_state") or {}
    return {
        "tool": tool_name,
        "inference_state": state.value,
        "allowed_interpretation_level": inf.get(
            "allowed_interpretation_level", "DESCRIPTIVE_ONLY"
        ),
        "interpretation": "not permitted",
        "forbidden_inference_flags": inf.get("forbidden_inference_flags") or [],
        "key_observations": [],
        "stat_result": None,
        "population": None,
        "metrics": {},
        "errors": [result["error"]] if result.get("error") else [],
    }


def build_output_schema(
    tool_name: str,
    result: Any,
    args: Optional[dict] = None,
) -> dict:
    args = args or {}
    if not isinstance(result, dict):
        return {
            "tool": tool_name,
            "inference_state": InferenceState.DESCRIPTIVE_ONLY.value,
            "allowed_interpretation_level": "DESCRIPTIVE_ONLY",
            "interpretation": "not permitted",
            "headline": f"{tool_name} completed",
            "metrics": {"plot": str(result)},
            "key_observations": [],
        }

    if result.get("error"):
        schema = _base_schema(tool_name, result, args)
        schema["headline"] = f"{tool_name} failed"
        schema["inference_state"] = InferenceState.BLOCKED.value
        schema["allowed_interpretation_level"] = "BLOCKED"
        return schema

    state = assign_inference_state(tool_name, result)
    inf = result.get("inference_state") or {}
    conclusion = inf.get("conclusion")

    if tool_name == "test_senescence_difference":
        ref = result.get("reference_age", "reference")
        comp = result.get("comparison_age", "comparison")
        ref_med = result.get("median_score_reference")
        comp_med = result.get("median_score_comparison")
        obs = []
        o = _observation_numeric_higher(ref, ref_med, comp, comp_med)
        if o:
            obs.append(o)

        effect = result.get("effect_size")
        validation_effect = None
        u_stat = result.get("u_statistic")
        n_comp = int((result.get("n_samples") or {}).get("comparison") or 0)
        n_ref = int((result.get("n_samples") or {}).get("reference") or 0)
        if u_stat is not None and n_comp and n_ref:
            validation_effect = round(1.0 - (2.0 * float(u_stat)) / (n_comp * n_ref), 4)

        schema = {
            "headline": "",
            "stat_result": {
                "test": result.get("test", "mannwhitneyu"),
                "p_value": result.get("p_value"),
                "effect_size_median_diff": effect,
                "effect_size_rank_biserial": validation_effect,
                "conclusion": conclusion or _conclusion_from_state(state),
                "alpha": 0.05,
                "significant_at_0_05": result.get("significant_at_0.05"),
            },
            "population": {
                "cell_type": result.get("cell_type") or args.get("cell_type"),
                "reference_age": ref,
                "comparison_age": comp,
                "n_samples": {
                    ref: result.get("n_samples", {}).get("reference"),
                    comp: result.get("n_samples", {}).get("comparison"),
                },
                "n_cells": {
                    ref: result.get("n_cells", {}).get("reference"),
                    comp: result.get("n_cells", {}).get("comparison"),
                },
                "sample_level_medians": result.get("sample_level_scores"),
                "statistical_unit": "biological_replicate",
                "sample_column": result.get("sample_column"),
            },
            "allowed_interpretation_level": inf.get("allowed_interpretation_level"),
            "inference_state": state.value,
            "key_observations": obs,
            "forbidden_inference_flags": inf.get("forbidden_inference_flags", []),
            "interpretation": "not permitted",
            "metrics": {
                f"median_score_{ref}": ref_med,
                f"median_score_{comp}": comp_med,
            },
            "warnings": result.get("warnings") or [],
            "tool": tool_name,
        }
        return schema

    if tool_name == "compare_across_age":
        ref = (result.get("age_contrast") or {}).get("reference_age")
        comp = (result.get("age_contrast") or {}).get("comparison_age")
        by_age = result.get("senescence_by_age") or result.get("global_senescence_by_age") or {}
        obs = []
        if ref and comp and ref in by_age and comp in by_age:
            o = _observation_numeric_higher(ref, by_age.get(ref), comp, by_age.get(comp))
            if o:
                obs.append(o)

        return {
            "headline": "",
            "stat_result": None,
            "population": {
                "cell_type": result.get("filtered_cell_type"),
                "age_groups": result.get("age_groups"),
                "n_cells_by_age": result.get("age_counts"),
                "statistical_unit": "cell",
            },
            "allowed_interpretation_level": "DESCRIPTIVE_ONLY",
            "inference_state": InferenceState.DESCRIPTIVE_ONLY.value,
            "key_observations": obs,
            "forbidden_inference_flags": inf.get("forbidden_inference_flags", []),
            "interpretation": "not permitted",
            "metrics": {
                "senescence_by_age": by_age,
                "most_senescent_per_celltype": result.get("most_senescent_per_celltype"),
            },
            "plots": [
                p for p in (
                    result.get("age_distribution_plot"),
                    result.get("senescence_violin_plot"),
                )
                if p
            ],
            "tool": tool_name,
        }

    if tool_name == "run_deseq2":
        rows = result.get("results") or []
        sig = [r for r in rows if _to_float(r.get("padj"), 1) < 0.05]
        return {
            "headline": "",
            "stat_result": {
                "test": "deseq2",
                "n_significant_fdr_0_05": len(sig),
                "conclusion": conclusion or _conclusion_from_state(state),
            },
            "population": {
                "cell_type": args.get("cell_type"),
                "youngest_group": result.get("youngest_group"),
                "oldest_group": result.get("oldest_group"),
                "n_samples": result.get("n_samples"),
                "samples_per_age": result.get("samples_per_age"),
                "statistical_unit": "pseudobulk_sample",
            },
            "allowed_interpretation_level": inf.get("allowed_interpretation_level"),
            "inference_state": state.value,
            "key_observations": [
                f"{len(sig)} gene(s) with padj < 0.05"
                if sig
                else "0 genes with padj < 0.05"
            ],
            "forbidden_inference_flags": inf.get("forbidden_inference_flags", []),
            "interpretation": "not permitted",
            "metrics": {
                "top_genes": rows[:10],
            },
            "tool": tool_name,
        }

    if tool_name == "senescence_score":
        return {
            "headline": "",
            "stat_result": None,
            "population": {"statistical_unit": "cell"},
            "allowed_interpretation_level": "DESCRIPTIVE_ONLY",
            "inference_state": InferenceState.DESCRIPTIVE_ONLY.value,
            "key_observations": [
                f"top_cluster={result.get('top_senescent_cluster')}",
                f"top_cell_type={result.get('top_senescent_cell_type')}",
            ],
            "forbidden_inference_flags": inf.get("forbidden_inference_flags", []),
            "interpretation": "not permitted",
            "metrics": {
                "genes_used": result.get("genes_used"),
                "mean_score": result.get("mean_score"),
                "max_score": result.get("max_score"),
                "cluster_scores": dict(list((result.get("cluster_scores") or {}).items())[:10]),
            },
            "plots": [result.get("plot_path")] if result.get("plot_path") else [],
            "tool": tool_name,
        }

    if tool_name == "find_senescence_markers":
        return {
            "headline": "",
            "stat_result": None,
            "population": {"species": result.get("species")},
            "allowed_interpretation_level": "DESCRIPTIVE_ONLY",
            "inference_state": InferenceState.DESCRIPTIVE_ONLY.value,
            "key_observations": [
                f"coverage_pct={result.get('coverage_pct')}",
                f"found={len(result.get('found_markers', []))}",
                f"missing={len(result.get('missing_markers', []))}",
            ],
            "interpretation": "not permitted",
            "metrics": {
                "found_markers": result.get("found_markers", [])[:30],
                "missing_markers": result.get("missing_markers", [])[:30],
            },
            "tool": tool_name,
        }

    if tool_name == "get_cluster_annotations":
        return {
            "headline": "",
            "stat_result": None,
            "allowed_interpretation_level": "DESCRIPTIVE_ONLY",
            "inference_state": InferenceState.DESCRIPTIVE_ONLY.value,
            "key_observations": [
                f"total_clusters={result.get('total_clusters')}",
            ],
            "interpretation": "not permitted",
            "metrics": {
                "cluster_annotations": dict(
                    list((result.get("cluster_annotations") or {}).items())[:20]
                ),
            },
            "tool": tool_name,
        }

    if tool_name == "generate_umap":
        path = result if isinstance(result, str) else result.get("plot_path")
        return {
            "headline": "",
            "stat_result": None,
            "allowed_interpretation_level": "DESCRIPTIVE_ONLY",
            "inference_state": InferenceState.DESCRIPTIVE_ONLY.value,
            "key_observations": ["umap_generated"],
            "interpretation": "not permitted",
            "metrics": {"plot_path": path},
            "tool": tool_name,
        }

    schema = _base_schema(tool_name, result, args)
    schema["headline"] = f"{tool_name} completed"
    return schema


def _conclusion_from_state(state) -> str:
    if state == InferenceState.LOW_POWER:
        return "no_conclusion"
    if state == InferenceState.NOT_SIGNIFICANT:
        return "not_significant"
    if state == InferenceState.SIGNIFICANT_INFERENTIAL:
        return "significant"
    return "descriptive_only"


def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
