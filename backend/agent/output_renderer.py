"""
Deterministic renderer: schema -> user text. NO LLM.

Produces clean Markdown for biologist-friendly display.
Enforces interpretation firewall from inference state machine.
"""

from __future__ import annotations

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


def _pct(value) -> str:
    if value is None:
        return "NA"
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return str(value)


# ── Tool-specific renderers ──────────────────────────────────────────────


def _render_markers(schema: dict) -> str:
    metrics = schema.get("metrics") or {}
    found = metrics.get("found_markers") or []
    missing = metrics.get("missing_markers") or []
    obs = schema.get("key_observations") or []

    # Extract coverage from observations
    coverage = "NA"
    for o in obs:
        if "coverage_pct=" in o:
            coverage = o.split("=")[1]

    total = len(found) + len(missing)
    lines = [
        f"### SenMayo Gene Coverage",
        "",
        f"**{len(found)}** of **{total}** SenMayo genes detected in this dataset ({_pct(coverage)} coverage).",
        "",
    ]

    if found:
        preview = ", ".join(found[:15])
        if len(found) > 15:
            preview += f", ... (+{len(found) - 15} more)"
        lines.append(f"**Detected:** {preview}")
        lines.append("")

    if float(coverage) < 30 if coverage != "NA" else True:
        lines.append("> **Note:** Low gene coverage may reduce the accuracy of senescence scoring.")
    elif float(coverage) >= 50:
        lines.append("> Good coverage for reliable senescence scoring.")

    return "\n".join(lines)


def _render_score(schema: dict) -> str:
    metrics = schema.get("metrics") or {}
    obs = schema.get("key_observations") or []

    top_cluster = None
    top_celltype = None
    for o in obs:
        if "top_cluster=" in o:
            top_cluster = o.split("=")[1]
        if "top_cell_type=" in o:
            top_celltype = o.split("=")[1]

    genes_used = metrics.get("genes_used")
    mean_score = _fmt(metrics.get("mean_score"))
    max_score = _fmt(metrics.get("max_score"))
    cluster_scores = metrics.get("cluster_scores") or {}

    lines = [
        f"### Senescence Scoring (SenMayo)",
        "",
    ]

    if top_celltype and top_celltype != "None":
        lines.append(f"**Highest senescence signal:** Cluster {top_cluster} ({top_celltype})")
    elif top_cluster:
        lines.append(f"**Highest senescence signal:** Cluster {top_cluster}")
    lines.append("")

    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Genes used | {genes_used} |")
    lines.append(f"| Mean score | {mean_score} |")
    lines.append(f"| Max score | {max_score} |")
    lines.append("")

    if cluster_scores:
        lines.append("**Scores by cluster** (top 8):")
        lines.append("")
        lines.append("| Cluster | Score |")
        lines.append("|---------|-------|")
        for label, score in list(cluster_scores.items())[:8]:
            lines.append(f"| {label} | {_fmt(score)} |")
        lines.append("")

    lines.append("> Scores are descriptive. Higher = stronger senescence-associated transcriptional signal.")

    return "\n".join(lines)


def _render_umap(schema: dict) -> str:
    return "### UMAP Visualization\n\nCluster UMAP plot generated. See the plots panel below."


def _render_annotations(schema: dict) -> str:
    metrics = schema.get("metrics") or {}
    annotations = metrics.get("cluster_annotations") or {}
    obs = schema.get("key_observations") or []

    total = None
    for o in obs:
        if "total_clusters=" in o:
            total = o.split("=")[1]

    lines = [
        f"### Cluster Cell Types",
        "",
        f"**{total or len(annotations)}** clusters identified.",
        "",
        "| Cluster | Dominant Cell Type |",
        "|---------|-------------------|",
    ]

    for cluster_id, cell_type in sorted(annotations.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
        lines.append(f"| {cluster_id} | {cell_type} |")

    return "\n".join(lines)


def _render_compare(schema: dict) -> str:
    pop = schema.get("population") or {}
    metrics = schema.get("metrics") or {}
    obs = schema.get("key_observations") or []

    cell_type = pop.get("cell_type")
    by_age = metrics.get("senescence_by_age") or {}
    most_sen = metrics.get("most_senescent_per_celltype") or {}
    n_cells_by_age = pop.get("n_cells_by_age") or {}

    lines = ["### Age Comparison", ""]

    if cell_type:
        lines.append(f"**Cell type:** {cell_type}")
        lines.append("")

    if by_age:
        lines.append("**Median SenMayo score by age:**")
        lines.append("")
        lines.append("| Age | Median Score | Cells |")
        lines.append("|-----|-------------|-------|")
        for age in sorted(by_age.keys()):
            cells = n_cells_by_age.get(age, "")
            lines.append(f"| {age} | {_fmt(by_age[age])} | {cells} |")
        lines.append("")

    if obs:
        for o in obs:
            lines.append(f"- {o}")
        lines.append("")

    if most_sen and not cell_type:
        lines.append("**Most senescent age per cell type** (top 5):")
        lines.append("")
        lines.append("| Cell Type | Peak Age | Score |")
        lines.append("|-----------|----------|-------|")
        for ct, info in list(sorted(most_sen.items(), key=lambda x: x[1].get("score", 0), reverse=True))[:5]:
            lines.append(f"| {ct} | {info.get('age')} | {_fmt(info.get('score'))} |")
        lines.append("")

    lines.append("> **Descriptive only** -- no p-values from this tool. Use `test_senescence_difference` for statistical testing.")

    return "\n".join(lines)


def _render_test(schema: dict) -> str:
    stat = schema.get("stat_result") or {}
    pop = schema.get("population") or {}
    metrics = schema.get("metrics") or {}
    state = schema.get("inference_state")
    conclusion = stat.get("conclusion")
    p = stat.get("p_value")
    ref = pop.get("reference_age", "reference")
    comp = pop.get("comparison_age", "comparison")
    cell_type = pop.get("cell_type", "NA")

    lines = ["### Senescence Score Test", ""]

    # Headline based on state
    if state == InferenceState.LOW_POWER.value or conclusion == "no_conclusion":
        lines.append(f"**Result: Underpowered** -- no statistically reliable conclusion for {cell_type}.")
    elif state == InferenceState.NOT_SIGNIFICANT.value or conclusion == "not_significant":
        lines.append(f"**Result: Not significant** (p = {_fmt(p)}) for {cell_type}.")
    elif state == InferenceState.SIGNIFICANT_INFERENTIAL.value or conclusion == "significant":
        lines.append(f"**Result: Significant** (p = {_fmt(p)}) for {cell_type}.")
    else:
        lines.append(f"**Result:** Test completed for {cell_type}.")
    lines.append("")

    # Key numbers table
    ref_med = metrics.get(f"median_score_{ref}")
    comp_med = metrics.get(f"median_score_{comp}")
    n_samples = pop.get("n_samples") or {}
    n_cells = pop.get("n_cells") or {}

    lines.append(f"| | {ref} (young) | {comp} (old) |")
    lines.append(f"|---|---|---|")
    lines.append(f"| **Median score** | {_fmt(ref_med)} | {_fmt(comp_med)} |")
    lines.append(f"| **Samples (mice)** | {n_samples.get(ref, 'NA')} | {n_samples.get(comp, 'NA')} |")
    lines.append(f"| **Cells** | {n_cells.get(ref, 'NA')} | {n_cells.get(comp, 'NA')} |")
    lines.append("")

    effect = stat.get("effect_size_median_diff")
    if effect is not None:
        lines.append(f"**Effect size** (median difference): {_fmt(effect)}")
        lines.append("")

    # Warnings
    for w in schema.get("warnings") or []:
        lines.append(f"> **Warning:** {w}")

    # Interpretation caution
    if conclusion == "no_conclusion":
        lines.append("")
        lines.append("> Too few biological replicates for a reliable test. Numeric trends reported only.")
    elif conclusion == "not_significant":
        lines.append("")
        lines.append("> Difference not statistically significant at alpha = 0.05. This does not prove absence of change.")

    lines.append("")
    lines.append(f"*Test: Mann-Whitney U on per-sample medians (not per-cell). Unit: biological replicate.*")

    return "\n".join(lines)


def _render_deseq2(schema: dict) -> str:
    stat = schema.get("stat_result") or {}
    pop = schema.get("population") or {}
    metrics = schema.get("metrics") or {}
    state = schema.get("inference_state")
    n_sig = stat.get("n_significant_fdr_0_05", 0)

    cell_type = pop.get("cell_type", "NA")
    youngest = pop.get("youngest_group", "young")
    oldest = pop.get("oldest_group", "old")

    lines = ["### Differential Expression (DESeq2)", ""]

    if state == InferenceState.NOT_SIGNIFICANT.value or n_sig == 0:
        lines.append(f"**No genes** passed FDR < 0.05 for {cell_type} ({oldest} vs {youngest}).")
        lines.append("")
        lines.append("Top ranked genes below are **exploratory only**.")
    elif state == InferenceState.LOW_POWER.value:
        lines.append(f"**{n_sig} gene(s)** with padj < 0.05 for {cell_type} -- but low sample count (exploratory).")
    else:
        lines.append(f"**{n_sig} gene(s)** with padj < 0.05 for {cell_type} ({oldest} vs {youngest}).")
    lines.append("")

    lines.append(f"Samples: {pop.get('n_samples', 'NA')} | Per-age: {pop.get('samples_per_age', 'NA')}")
    lines.append("")

    top_genes = metrics.get("top_genes") or []
    if top_genes:
        lines.append("| Gene | log2FC | padj |")
        lines.append("|------|--------|------|")
        for row in top_genes[:10]:
            gene = row.get("gene", "?")
            lfc = _fmt(row.get("log2FoldChange"))
            padj = _fmt(row.get("padj"))
            lines.append(f"| {gene} | {lfc} | {padj} |")
        lines.append("")

    lines.append(f"> Positive log2FC = higher expression in {oldest} group. Pseudobulk aggregation across samples.")

    return "\n".join(lines)


# ── Footer (audit info, collapsed in frontend) ──────────────────────────


def _footer(schema: dict) -> str:
    state = schema.get("inference_state", "")
    level = schema.get("allowed_interpretation_level", "")
    flags = schema.get("forbidden_inference_flags") or []
    flag_str = ", ".join(flags) if flags else "none"
    return (
        f"\n\n[System] inference_state={state} | "
        f"interpretation_level={level} | "
        f"forbidden=[{flag_str}]"
    )


# ── Main render entry point ──────────────────────────────────────────────


def render_strict_output(schema: dict) -> str:
    """Render one tool schema to final user-facing Markdown."""
    if schema.get("errors"):
        tool = schema.get("tool", "tool")
        errors = "; ".join(str(e) for e in schema["errors"])
        return f"**{tool}** could not run: {errors}"

    assert_render_allowed(schema)

    tool = schema.get("tool")

    if tool == "find_senescence_markers":
        body = _render_markers(schema)
    elif tool == "senescence_score":
        body = _render_score(schema)
    elif tool == "generate_umap":
        body = _render_umap(schema)
    elif tool == "get_cluster_annotations":
        body = _render_annotations(schema)
    elif tool == "compare_across_age":
        body = _render_compare(schema)
    elif tool == "test_senescence_difference":
        body = _render_test(schema)
    elif tool == "run_deseq2":
        body = _render_deseq2(schema)
    else:
        body = _render_generic(schema)

    return body + _footer(schema)


def _render_generic(schema: dict) -> str:
    tool = schema.get("tool", "tool")
    metrics = schema.get("metrics") or {}
    obs = schema.get("key_observations") or []

    lines = [f"### {tool}", ""]
    if obs:
        for o in obs:
            lines.append(f"- {o}")
        lines.append("")
    for k, v in metrics.items():
        if k == "cluster_scores" and isinstance(v, dict):
            lines.append("**Cluster scores:**")
            for ck, cv in list(v.items())[:10]:
                lines.append(f"- {ck}: {_fmt(cv)}")
        elif k == "plot_path":
            continue  # handled by plots panel
        else:
            lines.append(f"**{k}:** {v}")

    return "\n".join(lines)


# ── Public API (unchanged interface) ─────────────────────────────────────

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
    """Payload for Gemini after tools -- schema only, no prose task."""
    return {
        "strict_output_schema": schema,
        "instruction": (
            "Do not rewrite this as narrative. Tool selection only. "
            "User-facing text is produced by the deterministic renderer."
        ),
    }
