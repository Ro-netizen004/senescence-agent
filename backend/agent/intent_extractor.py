"""
Tier 2 intent extraction: LLM proposes a *structured* intent; a deterministic
validator confirms it against the real dataset before routing.

This replaces opaque LLM tool-calling with an auditable, schema-constrained
intent JSON. The LLM never invokes a tool and never writes user text — it only
emits a candidate {workflow, cell_type, ages}, which the validator checks
against the dataset (real cell types, real ages, allowed workflows) and maps to
a governed workflow. Invalid proposals are rejected, not executed.

Design: "LLM proposes, deterministic validator disposes." Downstream, the
admissibility and justification gates still apply regardless.
"""

from __future__ import annotations

import os
import json
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

from agent.intent_router import (
    RouteDecision,
    _available_cell_types,
    _order_ages_young_old,
)
from agent.workflows import WORKFLOWS

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))
_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
if os.getenv("GEMINI_API_KEY"):
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Workflows the extractor is allowed to propose (must exist in WORKFLOWS).
_ROUTABLE_WORKFLOWS = (
    "panel", "coverage", "score_and_annotate",
    "senescence_test", "deseq2", "umap", "cluster_annotations",
)
# Workflows that require a valid cell type + age contrast to run.
_CONTRAST_WORKFLOWS = ("senescence_test", "deseq2")

_INTENT_SCHEMA_HINT = """Return ONLY a JSON object with these fields:
{
  "workflow": one of ["panel","coverage","score_and_annotate","senescence_test","deseq2","umap","cluster_annotations","none"],
  "cell_type": a cell type from the AVAILABLE list, or null,
  "reference_age": an age from the AVAILABLE ages, or null,
  "comparison_age": an age from the AVAILABLE ages, or null
}
Workflow meanings:
- panel: full standard senescence analysis (markers + score + umap + annotations + age comparison)
- coverage: SenMayo gene coverage only
- score_and_annotate: senescence score + cluster cell types
- senescence_test: STATISTICAL test of senescence score difference between two ages for one cell type
- deseq2: pseudobulk differential expression between two ages for one cell type
- umap: UMAP plot only
- cluster_annotations: cell type per cluster
- none: conceptual/definitional question, or unclear
Only use cell_type / ages that appear in the AVAILABLE lists. If none apply, use null.
Do not invent values. Output JSON only, no prose."""


def _dataset_context(adata) -> str:
    profile = (adata.uns.get("dataset_profile") or {}) if adata is not None else {}
    cts = _available_cell_types(adata) if adata is not None else []
    ages = profile.get("age_values") or []
    return (
        f"AVAILABLE cell types: {cts[:40]}\n"
        f"AVAILABLE ages: {ages}\n"
    )


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    t = text.strip()
    # Strip code fences if present
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    t = t.strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, ValueError):
        # last resort: find first {...} block
        start, end = t.find("{"), t.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(t[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                return {}
    return {}


def extract_intent(message: str, adata) -> dict:
    """
    Ask the LLM for a structured intent JSON. Returns {} on any failure
    (caller falls back to the existing Gemini tool-calling loop).
    """
    if not os.getenv("GEMINI_API_KEY"):
        return {}
    try:
        model = genai.GenerativeModel(
            model_name=_MODEL,
            generation_config=genai.GenerationConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        prompt = (
            f"{_INTENT_SCHEMA_HINT}\n\n"
            f"{_dataset_context(adata)}\n"
            f"User message: {message!r}\n"
        )
        from agent.rate_limit import throttle
        throttle()
        resp = model.generate_content(prompt)
        return _parse_json(resp.text)
    except Exception as e:  # network, quota, parse — all non-fatal
        print(f"intent extraction failed: {e}")
        return {}


def validate_and_route(intent: dict, adata) -> Optional[RouteDecision]:
    """
    Deterministically validate the LLM's proposed intent against the real
    dataset. Returns a RouteDecision only if valid; else None (defer).
    """
    if not isinstance(intent, dict):
        return None

    workflow = str(intent.get("workflow") or "").strip()
    if workflow not in _ROUTABLE_WORKFLOWS or workflow not in WORKFLOWS:
        return None

    # Workflows with no required args route immediately.
    if workflow not in _CONTRAST_WORKFLOWS:
        return RouteDecision(workflow_id=workflow)

    # Contrast workflows need a VALID cell type present in the dataset.
    from tools.age_analysis import _resolve_cell_type
    available = _available_cell_types(adata)
    proposed_ct = intent.get("cell_type")
    resolved_ct = _resolve_cell_type(str(proposed_ct), available) if proposed_ct else None
    if not resolved_ct:
        return None  # can't run a group test without a real population

    # Validate ages against the dataset; fall back to profile extremes.
    profile = (adata.uns.get("dataset_profile") or {})
    age_values = [str(a) for a in (profile.get("age_values") or [])]
    ref = intent.get("reference_age")
    comp = intent.get("comparison_age")

    def _valid_age(a):
        return a is not None and (not age_values or str(a) in age_values)

    if not (_valid_age(ref) and _valid_age(comp)) or str(ref) == str(comp):
        ref = profile.get("youngest") or "3m"
        comp = profile.get("oldest") or "24m"

    ref, comp = _order_ages_young_old(str(ref), str(comp))

    tool_name = "run_deseq2" if workflow == "deseq2" else "test_senescence_difference"
    return RouteDecision(
        workflow_id=workflow,
        tool_args={
            tool_name: {
                "cell_type": resolved_ct,
                "reference_age": ref,
                "comparison_age": comp,
            }
        },
        reply_suffix=(
            f"[System] Routed via structured intent: {workflow} "
            f"({resolved_ct}, {ref} vs {comp})."
        ),
    )
