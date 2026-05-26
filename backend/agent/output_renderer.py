"""
Deterministic renderer: schema → user text. NO LLM.

Enforces interpretation firewall from inference state machine.
"""

from __future__ import annotations

import json
import os
from typing import Any

from agent.inference_state import InferenceState, InterpretationLevel


class InterpretationFirewallError(Exception):
    pass


def assert_render_allowed(schema: dict) -> None:
    level = schema.get("allowed_interpretation_level")
    if level == InterpretationLevel.BLOCKED.value:
        if schema.get("errors"):
            return
        raise InterpretationFirewallError("BLOCKED state: no render except error payload")
    if schema.get("interpretation") != "not permitted":
        raise InterpretationFirewallError(
            "interpretation field must be 'not permitted' for deterministic render"
        )


def _fmt(value, digits=4) -> str:
    if value is None:
        return "NA"
    try:
        n = float(value)
        if n != n:
            return "NA"
        return f"{n:.{digits}g}"
    except (TypeError, ValueError):
        return str(value)


def _headline_for_test(schema: dict) -> str:
    state = schema.get("inference_state")
    stat = schema.get("stat_result") or {}
    conclusion = stat.get("conclusion")
    p = stat.get("p_value")

    if state == InferenceState.LOW_POWER.value or conclusion == "no_conclusion":
        return "Senescence score test: no statistically reliable conclusion (underpowered)."
    if state == InferenceState.NOT_SIGNIFICANT.value or conclusion == "not_significant":
        return f"Senescence score test: not statistically significant (p={_fmt(p)})."
    if state == InferenceState.SIGNIFICANT_INFERENTIAL.value:
        return f"Senescence score test: statistically significant at alpha=0.05 (p={_fmt(p)})."
    return "Senescence score test completed."


def _body_test(schema: dict) -> list[str]:
    stat = schema.get("stat_result") or {}
    pop = schema.get("population") or {}
    ref = pop.get("reference_age", "reference")
    comp = pop.get("comparison_age", "comparison")
    conclusion = stat.get("conclusion")
    p = stat.get("p_value")
    lines = []

    if conclusion == "no_conclusion":
        lines.append(
            "No statistically reliable difference detected. Report numeric results only."
        )
    elif conclusion == "not_significant":
        lines.append(
            f"Difference observed in sample medians but not statistically significant (p={_fmt(p)})."
        )
    elif conclusion == "significant":
        lines.append(
            f"Sample-level median scores differ significantly at alpha=0.05 (p={_fmt(p)})."
        )

    lines.extend([
        "",
        f"Test: {stat.get('test', 'mannwhitneyu')} | Unit: {pop.get('statistical_unit')}",
        f"Cell type: {pop.get('cell_type', 'NA')}",
        f"Contrast: {comp} vs {ref}",
        f"n_samples: {pop.get('n_samples')}",
        f"n_cells: {pop.get('n_cells')}",
        f"median_score_{ref}: {_fmt(schema.get('metrics', {}).get(f'median_score_{ref}'))}",
        f"median_score_{comp}: {_fmt(schema.get('metrics', {}).get(f'median_score_{comp}'))}",
        f"effect_size (median difference): {_fmt(stat.get('effect_size_median_diff'))}",
        f"p-value: {_fmt(p)}",
        f"significant_at_0.05: {stat.get('significant_at_0_05')}",
    ])

    medians = pop.get("sample_level_medians")
    if medians:
        lines.append(f"per_sample_medians_{ref}: {medians.get('reference')}")
        lines.append(f"per_sample_medians_{comp}: {medians.get('comparison')}")

    if schema.get("key_observations"):
        lines.extend(["", "Observations (numeric only):"])
        for o in schema["key_observations"]:
            lines.append(f"- {o}")

    for w in schema.get("warnings") or []:
        lines.append(f"Warning: {w}")

    lines.extend(_footer(schema))
    return lines


def _body_compare(schema: dict) -> list[str]:
    lines = [
        "Age-stratified SenMayo scores (descriptive only; no p-value from this tool).",
        "",
    ]
    pop = schema.get("population") or {}
    if pop.get("cell_type"):
        lines.append(f"Cell type: {pop['cell_type']}")
    if pop.get("n_cells_by_age"):
        lines.append(f"Cell counts by age: {pop['n_cells_by_age']}")
    metrics = schema.get("metrics") or {}
    if metrics.get("senescence_by_age"):
        lines.append(f"Median scores by age: {metrics['senescence_by_age']}")

    if schema.get("key_observations"):
        lines.extend(["", "Observations (numeric only):"])
        for o in schema["key_observations"]:
            lines.append(f"- {o}")

    plots = schema.get("plots") or []
    if plots:
        lines.append("Plots: " + ", ".join(os.path.basename(p) for p in plots))

    lines.extend(_footer(schema))
    return lines


def _body_deseq2(schema: dict) -> list[str]:
    stat = schema.get("stat_result") or {}
    n_sig = stat.get("n_significant_fdr_0_05", 0)
    state = schema.get("inference_state")

    if state == InferenceState.NOT_SIGNIFICANT.value or n_sig == 0:
        lines = [
            "DESeq2: no genes met FDR < 0.05 at pseudobulk level.",
            "Top ranked genes are exploratory only.",
        ]
    elif state == InferenceState.LOW_POWER.value:
        lines = [
            f"DESeq2: {n_sig} gene(s) with padj < 0.05 (low sample count — exploratory).",
        ]
    else:
        lines = [f"DESeq2: {n_sig} gene(s) with padj < 0.05."]

    pop = schema.get("population") or {}
    lines.extend([
        "",
        f"Cell type: {pop.get('cell_type', 'NA')}",
        f"Contrast: {pop.get('oldest_group')} vs {pop.get('youngest_group')}",
        f"n_samples: {pop.get('n_samples')}",
        f"samples_per_age: {pop.get('samples_per_age')}",
    ])

    for row in (schema.get("metrics") or {}).get("top_genes") or []:
        lines.append(
            f"- {row.get('gene')}: log2FC {_fmt(row.get('log2FoldChange'))}, "
            f"padj {_fmt(row.get('padj'))}"
        )

    lines.extend(_footer(schema))
    return lines


def _body_generic(schema: dict) -> list[str]:
    lines = [schema.get("headline") or f"{schema.get('tool')} completed", ""]
    if schema.get("key_observations"):
        lines.append("Observations:")
        for o in schema["key_observations"]:
            lines.append(f"- {o}")
    metrics = schema.get("metrics") or {}
    for k, v in metrics.items():
        if k == "cluster_scores" and isinstance(v, dict):
            lines.append("Cluster scores:")
            for ck, cv in list(v.items())[:10]:
                lines.append(f"  {ck}: {_fmt(cv)}")
        elif k not in ("top_genes",):
            lines.append(f"{k}: {v}")
    plots = schema.get("plots") or []
    if plots:
        lines.append("Plots: " + ", ".join(os.path.basename(str(p)) for p in plots))
    lines.extend(_footer(schema))
    return lines


def _footer(schema: dict) -> list[str]:
    flags = schema.get("forbidden_inference_flags") or []
    level = schema.get("allowed_interpretation_level")
    return [
        "",
        f"[System] inference_state={schema.get('inference_state')} | "
        f"interpretation_level={level}",
        f"[System] interpretation={schema.get('interpretation', 'not permitted')}",
        "Forbidden: " + ", ".join(flags) if flags else "",
    ]


def render_strict_output(schema: dict) -> str:
    """Render one tool schema to final user text."""
    if schema.get("errors"):
        return (
            f"**{schema.get('tool', 'tool')}** failed: "
            + "; ".join(str(e) for e in schema["errors"])
        )

    assert_render_allowed(schema)

    tool = schema.get("tool")
    if tool == "test_senescence_difference":
        schema = {**schema, "headline": _headline_for_test(schema)}
        return "\n".join([schema["headline"], ""] + _body_test(schema))

    if tool == "compare_across_age":
        schema["headline"] = "Age comparison (descriptive only)."
        return "\n".join([schema["headline"], ""] + _body_compare(schema))

    if tool == "run_deseq2":
        state = schema.get("inference_state")
        if state == InferenceState.NOT_SIGNIFICANT.value:
            schema["headline"] = "Gene expression: no FDR-significant genes."
        else:
            schema["headline"] = "Gene expression (pseudobulk DESeq2)."
        return "\n".join([schema["headline"], ""] + _body_deseq2(schema))

    schema.setdefault("headline", f"{tool} completed.")
    return "\n".join([schema["headline"], ""] + _body_generic(schema))


from agent.output_schema import build_output_schema


def build_schema_from_log(name: str, args: dict, result: Any) -> dict:
    return build_output_schema(name, result, args)


def render_tool_calls_with_schema(tool_calls: list[dict]) -> tuple[str, list[dict]]:
    """Return (reply_text, schemas) for logging/API."""
    schemas = []
    for entry in tool_calls:
        schema = build_schema_from_log(
            entry.get("name"),
            entry.get("args") or {},
            entry.get("result"),
        )
        schemas.append(schema)
    text = "\n\n---\n\n".join(render_strict_output(s) for s in schemas)
    return text, schemas


def schema_json_for_llm(schema: dict) -> dict:
    """Payload for Gemini after tools — schema only, no prose task."""
    return {
        "strict_output_schema": schema,
        "instruction": (
            "Do not rewrite this as narrative. Tool selection only. "
            "User-facing text is produced by the deterministic renderer."
        ),
    }
