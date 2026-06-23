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
    return ("leiden" in text or "each cluster" in text) and (
        "cell type" in text or "cell-type" in text
    )


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
    for ct in _available_cell_types(adata):
        if ct.lower() in text:
            return ct

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
            from tools.age_analysis import _resolve_cell_type

            resolved = _resolve_cell_type(canonical, _available_cell_types(adata))
            return resolved or canonical
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
            "differentially expressed",
        )
    )


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
        cell_type = _infer_cell_type_for_test(message, adata)
        if cell_type:
            ref, comp = _order_ages_young_old(*_parse_age_contrast(message, profile))
            return RouteDecision(
                workflow_id="deseq2",
                tool_args={
                    "run_deseq2": {
                        "cell_type": cell_type,
                        "reference_age": ref,
                        "comparison_age": comp,
                    }
                },
            )

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
