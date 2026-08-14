"""Map user messages to workflow templates or concept answers (no Gemini)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_CONCEPT_ANSWERS: dict[str, str] = {
    "senmayo": (
        "### What the SenMayo score is\n\n"
        "**SenMayo** is a curated set of ~125 senescence-associated genes "
        "(Saul et al., 2022, *Nature Communications*), dominated by senescence-associated "
        "secretory phenotype (SASP) factors such as cytokines, chemokines, and growth factors.\n\n"
        "The **senescence score** is computed per cell with Scanpy's `score_genes`: it is the "
        "mean expression of the detected SenMayo genes minus the mean of a matched reference "
        "gene set. A higher score means a stronger senescence-associated transcriptional signal.\n\n"
        "> This score is **relative and descriptive** -- it ranks cells and clusters by signature "
        "strength. It is not a binary senescent vs. non-senescent label, and a score alone does "
        "not establish statistical significance. Use a statistical test "
        "(`test_senescence_difference`) for a governed comparison between groups."
    ),
}


@dataclass
class RouteDecision:
    workflow_id: str | None = None
    tool_args: dict[str, dict[str, Any]] | None = None
    concept_reply: str | None = None
    reply_suffix: str | None = None


def _wants_analysis_panel(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "run everything",
            "run all",
            "run the full",
            "full analysis",
            "analyze everything",
            "complete analysis",
            "comprehensive analysis",
            "end-to-end",
            "what's interesting",
            "whats interesting",
            "what is interesting",
            "tell me what's interesting",
        )
    )


def _needs_pvalue_clarification(message: str) -> bool:
    text = message.lower()
    return any(
        w in text
        for w in (
            "p-value",
            "p value",
            "pvalue",
            "p-values",
            "statistical significance",
            "significant difference",
            "exact p",
        )
    )


def _wants_umap(message: str) -> bool:
    return "umap" in message.lower()


def _wants_cluster_annotations(message: str) -> bool:
    text = message.lower()
    mentions_cluster = "leiden" in text or "cluster" in text or "each cluster" in text
    mentions_celltype = "cell type" in text or "cell-type" in text or "celltype" in text
    # "annotate the clusters", "identify cell types", "what cell types are here"
    if "annotat" in text and mentions_cluster:
        return True
    if ("identify" in text or "label" in text or "what" in text) and mentions_celltype:
        return True
    return mentions_cluster and mentions_celltype


def _cell_type_column(adata) -> str:
    for col in ("cell_ontology_class", "cell_type", "celltype"):
        if col in adata.obs.columns:
            return col
    return "cell_ontology_class"


def _available_cell_types(adata) -> list[str]:
    col = _cell_type_column(adata)
    if col not in adata.obs.columns:
        return []
    return sorted(adata.obs[col].astype(str).unique().tolist())


def _message_mentions_cell_type(message: str, adata) -> bool:
    text = message.lower()
    for ct in _available_cell_types(adata):
        if ct.lower() in text:
            return True
    aliases = (
        "neuron",
        "neurons",
        "t cell",
        "t cells",
        "macrophage",
        "macrophages",
        "mesangial",
    )
    return any(alias in text for alias in aliases)


def _parse_age_contrast(message: str, profile: dict | None = None) -> tuple[str, str]:
    profile = profile or {}
    youngest = profile.get("youngest") or "3m"
    oldest = profile.get("oldest") or "24m"
    age_format = profile.get("age_format")
    age_values = profile.get("age_values") or []

    text = message.lower()

    if age_format == "months_m":
        ages = re.findall(r"\b(\d+m)\b", message, flags=re.I)
        if len(ages) >= 2:
            return ages[0].lower(), ages[1].lower()

    elif age_format == "years_int":
        candidates = re.findall(r"\b(\d{2,3})\b", message)
        matched = [c for c in candidates if c in age_values]
        if len(matched) >= 2:
            return matched[0], matched[1]

    elif age_format == "label" and age_values:
        for val in age_values:
            if val.lower() in text:
                # found one label — check for a second
                others = [v for v in age_values if v.lower() in text and v != val]
                if others:
                    return val, others[0]

    # semantic young/old → use inferred extremes from profile
    if ("young" in text or "younger" in text) and ("old" in text or "aged" in text or "elderly" in text):
        return youngest, oldest

    return youngest, oldest


def _infer_cell_type_for_test(message: str, adata) -> str | None:
    text = message.lower()
    available = _available_cell_types(adata)

    # 1. Exact full-name mention.
    for ct in available:
        if ct.lower() in text:
            return ct

    # 2. Extract the phrase after "on"/"for" (up to a contrast keyword) and resolve
    #    it, so "on fibroblast cells comparing ..." -> "fibroblast of cardiac tissue".
    from tools.text_match import resolve_cell_type
    m = re.search(
        r"\b(?:on|for)\s+(.+?)(?:\s+(?:between|comparing|compare|vs\.?|versus|across|by|,)|$)",
        text,
    )
    if m:
        resolved = resolve_cell_type(m.group(1).strip(), available)
        if resolved:
            return resolved

    aliases = {
        "neurons": "neuron",
        "neuron": "neuron",
        "t cells": "T cell",
        "t cell": "T cell",
        "macrophages": "macrophage",
        "macrophage": "macrophage",
        "mesangial cells": "mesangial cell",
        "mesangial cell": "mesangial cell",
    }
    for alias, canonical in aliases.items():
        if alias in text:
            from tools.text_match import resolve_cell_type

            # Only return the alias if it actually exists in THIS dataset — never
            # fabricate a cell type the data doesn't contain (e.g. "T cell" in an
            # aorta dataset that has none).
            return resolve_cell_type(canonical, _available_cell_types(adata))
    return None


def _is_bare_pvalue_request(message: str, adata) -> bool:
    if not _needs_pvalue_clarification(message):
        return False
    return not _message_mentions_cell_type(message, adata)


def _wants_explicit_senescence_test(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "test senescence difference",
            "senescence difference for",
            "senescence difference in",
            "test_senescence_difference",
        )
    )


def _wants_deseq2(message: str) -> bool:
    text = message.lower()
    return any(
        phrase in text
        for phrase in (
            "deseq2",
            "deseq",
            "differential expression",
            "differential analysis",
            "differentially expressed",
            "genes differ",
        )
    )


# "Run differential expression on <cell type> between <Group A> and <Group B>"
_DE_TEMPLATE_RE = re.compile(
    r"(?:differential\s+(?:gene\s+)?(?:expression|analysis)|deseq2?)\b"
    r".*?\b(?:on|for|in)\s+(?P<ct>.+?)\s+between\s+(?P<g1>.+?)\s+(?:and|vs\.?|versus)\s*(?P<g2>.+?)[.!?\s]*$",
    re.IGNORECASE,
)


def _has_two_age_tokens(message: str) -> bool:
    return len(re.findall(r"\b\d+\s*m\b", message, flags=re.I)) >= 2


def _resolve_group_pair(g1: str, g2: str, profile: dict) -> tuple[str, str, str] | None:
    """Find the grouping column (age/condition/treatment/...) that contains BOTH
    named group values, returning (group_column, ref_value, comp_value) with the
    dataset's exact casing. Returns None if no single column contains both."""
    g1n, g2n = str(g1).strip().lower(), str(g2).strip().lower()
    if g1n == g2n:
        return None
    for gc in (profile.get("group_columns") or []):
        vals = {str(v).strip().lower(): str(v) for v in gc.get("values", [])}
        if g1n in vals and g2n in vals:
            return gc["column"], vals[g1n], vals[g2n]
    return None


def _parse_deseq2_template(message: str, adata, profile: dict) -> dict | None:
    """Parse the fill-in template into a validated {cell_type, group_column,
    reference_group, comparison_group}. Returns None if the cell type or the two
    groups can't be resolved against the real dataset."""
    m = _DE_TEMPLATE_RE.search(message)
    if not m:
        return None
    from tools.text_match import resolve_cell_type
    cell_type = resolve_cell_type(m.group("ct").strip(), _available_cell_types(adata))
    if not cell_type:
        return None
    pair = _resolve_group_pair(m.group("g1"), m.group("g2"), profile)
    if not pair:
        return None
    group_column, ref, comp = pair
    return {
        "cell_type": cell_type,
        "group_column": group_column,
        "reference_group": ref,
        "comparison_group": comp,
    }


def _deseq2_clarification(adata, profile: dict) -> str:
    """Deterministic 'ask + template' reply listing the real cell types and
    grouping variables the user can pick from."""
    cts = _available_cell_types(adata)
    ct_preview = ", ".join(cts[:8]) + (f", … ({len(cts)} total)" if len(cts) > 8 else "")
    gcs = profile.get("group_columns") or []

    lines = [
        "### Differential expression — which contrast?",
        "",
        "I can run pseudobulk DESeq2, but I need the exact comparison. Fill in this template:",
        "",
        "```",
        "Run differential expression on <cell type> between <Group A> and <Group B>",
        "```",
        "",
        f"**Available cell types:** {ct_preview or '(none detected)'}",
        "",
        "**Grouping variables you can compare:**",
    ]
    primary = profile.get("primary_group_column")
    if gcs:
        # List the recommended (testable) grouping first.
        ordered = sorted(gcs, key=lambda g: g["column"] != primary)
        for gc in ordered[:6]:
            vals = ", ".join(map(str, gc["values"][:12]))
            tag = "  _(recommended)_" if gc["column"] == primary else ""
            lines.append(f"- **{gc['column']}** — {vals}{tag}")
    else:
        lines.append(
            "- _(no grouping column with ≥2 groups detected — DESeq2 needs a "
            "condition / age / treatment column defined at the sample level)_"
        )

    # Example uses the recommended grouping's own values (not two single-sample
    # values that would fail as pseudoreplication).
    primary_gc = next((g for g in gcs if g["column"] == primary), gcs[0] if gcs else None)
    if cts and primary_gc and len(primary_gc.get("values") or []) >= 2:
        ex_ct, ex_vals = cts[0], primary_gc["values"]
        lines += [
            "",
            f"_Example:_ `Run differential expression on {ex_ct} between "
            f"{ex_vals[0]} and {ex_vals[1]}`",
            "",
            "_Tip: use the **Dataset setup** table at the top to define custom groups "
            "(e.g. treat several conditions as one 'control' group)._",
        ]
    return "\n".join(lines)


def _order_ages_young_old(ref: str, comp: str) -> tuple[str, str]:
    def months(value: str) -> int:
        m = re.match(r"(\d+)", value or "")
        return int(m.group(1)) if m else 0

    return (ref, comp) if months(ref) <= months(comp) else (comp, ref)


def _is_definitional_question(message: str) -> bool:
    text = message.lower().strip()
    triggers = (
        "what is",
        "what's",
        "what are",
        "explain",
        "define",
        "definition of",
        "tell me about",
        "what does",
        "how does",
    )
    if not any(t in text for t in triggers):
        return False
    dataset_terms = (
        "in this dataset",
        "coverage",
        "in these cells",
        "which cluster",
        "p-value",
        "p value",
        "median",
        "score cells",
        "highest",
        "compare",
        "deseq",
    )
    return not any(d in text for d in dataset_terms)


def _try_concept_answer(message: str) -> dict | None:
    if not _is_definitional_question(message):
        return None
    text = message.lower()
    if "senmayo" in text or "senescence score" in text or (
        "senescence" in text and "score" in text
    ):
        return {"reply": _CONCEPT_ANSWERS["senmayo"], "plots": [], "tool_calls": []}
    return None


def _wants_coverage(message: str) -> bool:
    text = message.lower()
    return "coverage" in text and ("senmayo" in text or "marker" in text)


def _wants_score_and_annotate(message: str) -> bool:
    text = message.lower()
    return "score" in text and ("cluster" in text or "highest" in text)


def route(message: str, adata) -> RouteDecision:
    """Pick a workflow template, concept answer, or defer to Gemini (workflow_id=None)."""
    profile = (adata.uns.get("dataset_profile") or {}) if adata is not None else {}

    concept = _try_concept_answer(message)
    if concept is not None:
        return RouteDecision(concept_reply=concept["reply"])

    if _wants_analysis_panel(message):
        return RouteDecision(workflow_id="panel")

    if _wants_coverage(message):
        return RouteDecision(workflow_id="coverage")

    if _wants_score_and_annotate(message):
        return RouteDecision(workflow_id="score_and_annotate")

    if _wants_deseq2(message):
        # 1) Explicit template: "... on <cell type> between <Group A> and <Group B>"
        parsed = _parse_deseq2_template(message, adata, profile)
        if parsed:
            return RouteDecision(
                workflow_id="deseq2",
                tool_args={"run_deseq2": {
                    "cell_type": parsed["cell_type"],
                    "group_column": parsed["group_column"],
                    "reference_group": parsed["reference_group"],
                    "comparison_group": parsed["comparison_group"],
                    "covariates": list(profile.get("deseq2_covariates") or []),
                }},
                reply_suffix=(
                    f"[System] Contrast: differential expression on {parsed['cell_type']} "
                    f"by {parsed['group_column']} "
                    f"({parsed['reference_group']} vs {parsed['comparison_group']})."
                ),
            )
        # 2) Resolve two group values explicitly named in ordinary language.
        # This must precede age fallback: a dataset can contain a real age column
        # while the user explicitly requests a different factor such as null_group.
        cell_type = _infer_cell_type_for_test(message, adata)
        message_lower = message.lower()
        named_pairs = []
        for group in profile.get("group_columns") or []:
            mentioned = [
                str(value) for value in (group.get("values") or [])
                if str(value).lower() in message_lower
            ]
            if len(mentioned) == 2:
                # The user's order defines reference then comparison. Dataset
                # profile values may be lexicographically sorted (24m before
                # 3m), which must never reverse the requested contrast.
                mentioned.sort(key=lambda value: message_lower.find(value.lower()))
                named_pairs.append((group["column"], mentioned[0], mentioned[1]))
        if cell_type and len(named_pairs) == 1:
            group_column, ref, comp = named_pairs[0]
            args = {
                "cell_type": cell_type,
                "group_column": group_column,
                "reference_group": ref,
                "comparison_group": comp,
                "covariates": list(profile.get("deseq2_covariates") or []),
            }
            return RouteDecision(
                workflow_id="deseq2",
                tool_args={"run_deseq2": args},
                reply_suffix=(
                    f"[System] Contrast: differential expression on {cell_type} "
                    f"by {group_column} ({ref} vs {comp})."
                ),
            )

        # 3) Auto-run when the contrast is unambiguous: an age grouping (youngest
        #    vs oldest) or a grouping variable with exactly two levels.
        has_age = bool(profile.get("age_column")) or _has_two_age_tokens(message)
        primary = profile.get("primary_group_column")
        primary_gc = next(
            (g for g in (profile.get("group_columns") or []) if g["column"] == primary),
            None,
        )
        two_level = bool(primary_gc and len(primary_gc.get("values") or []) == 2)
        if cell_type and (has_age or two_level):
            if has_age:
                ref, comp = _order_ages_young_old(*_parse_age_contrast(message, profile))
                args = {"cell_type": cell_type, "reference_age": ref, "comparison_age": comp}
                conf = f"by age ({ref} vs {comp})"
            else:
                vals = primary_gc["values"]
                args = {
                    "cell_type": cell_type,
                    "group_column": primary,
                    "reference_group": vals[0],
                    "comparison_group": vals[1],
                }
                conf = f"by {primary} ({vals[0]} vs {vals[1]})"
            args["covariates"] = list(profile.get("deseq2_covariates") or [])
            return RouteDecision(
                workflow_id="deseq2",
                tool_args={"run_deseq2": args},
                reply_suffix=f"[System] Contrast: differential expression on {cell_type} {conf}.",
            )
        # 3) Underspecified → deterministic clarification (template + real options).
        return RouteDecision(concept_reply=_deseq2_clarification(adata, profile))

    if _wants_umap(message):
        return RouteDecision(workflow_id="umap")

    if _wants_cluster_annotations(message):
        return RouteDecision(workflow_id="cluster_annotations")

    if _is_bare_pvalue_request(message, adata):
        ref, comp = _parse_age_contrast(message, profile)
        default_ct = _infer_cell_type_for_test(message, adata) or "T cell"
        return RouteDecision(
            workflow_id="senescence_test",
            tool_args={
                "test_senescence_difference": {
                    "cell_type": default_ct,
                    "reference_age": ref,
                    "comparison_age": comp,
                }
            },
            reply_suffix=(
                f"[System] Default contrast: {default_ct} {ref} vs {comp} "
                "(question did not specify cell type or ages)."
            ),
        )

    if _wants_explicit_senescence_test(message) or (
        _needs_pvalue_clarification(message) and _message_mentions_cell_type(message, adata)
    ):
        cell_type = _infer_cell_type_for_test(message, adata)
        if cell_type:
            ref, comp = _parse_age_contrast(message, profile)
            return RouteDecision(
                workflow_id="senescence_test",
                tool_args={
                    "test_senescence_difference": {
                        "cell_type": cell_type,
                        "reference_age": ref,
                        "comparison_age": comp,
                    }
                },
            )

    return RouteDecision()
