"""Dataset-grounded analysis planning with deterministic validation.

The LLM may propose the scientific analysis plan, but only a validated plan can
alter tool arguments.  The returned audit always records the proposal, any
corrections, and the exact plan used for execution.
"""

from __future__ import annotations

import json
import os
from typing import Any

from google import genai
from google.genai import types

from agent.intent_router import RouteDecision, _available_cell_types


_METHOD_FOR_WORKFLOW = {
    "deseq2": "pseudobulk_deseq2",
    "senescence_test": "sample_level_senescence_score_test",
}


def _tool_for_workflow(workflow_id: str) -> str | None:
    return {
        "deseq2": "run_deseq2",
        "senescence_test": "test_senescence_difference",
    }.get(workflow_id)


def _route_args(decision: RouteDecision) -> dict[str, Any]:
    tool = _tool_for_workflow(decision.workflow_id or "")
    return dict(((decision.tool_args or {}).get(tool) or {})) if tool else {}


def _sample_level_covariates(adata, profile: dict) -> list[str]:
    sample = profile.get("sample_column")
    if not sample or sample not in adata.obs.columns:
        return []
    excluded = {
        sample, profile.get("cell_type_column"), profile.get("primary_group_column"),
        "comparison_group",
    }
    n_samples = adata.obs[sample].astype(str).nunique()
    options = []
    for column in adata.obs.columns:
        if column in excluded:
            continue
        per_sample = adata.obs.groupby(sample, observed=True)[column].nunique(dropna=False)
        levels = adata.obs[column].nunique(dropna=False)
        if not per_sample.empty and per_sample.max() == 1 and 1 < levels < n_samples:
            options.append(str(column))
    return options


def _baseline_plan(decision: RouteDecision, profile: dict) -> dict[str, Any]:
    args = _route_args(decision)
    group = args.get("group_column") or args.get("age_column") or profile.get("primary_group_column")
    reference = args.get("reference_group") or args.get("reference_age")
    comparison = args.get("comparison_group") or args.get("comparison_age")
    return {
        "method": _METHOD_FOR_WORKFLOW.get(decision.workflow_id or ""),
        "cell_type": args.get("cell_type"),
        "unit_of_replication": args.get("sample_column") or profile.get("sample_column"),
        "group_column": group,
        "reference_group": reference,
        "comparison_group": comparison,
        "covariates": list(args.get("covariates") or profile.get("deseq2_covariates") or []),
        "excluded_covariates": {},
        "rationale": "Deterministic dataset-grounded route.",
        "expected_limitations": [],
    }


def _parse_json(text: str) -> dict:
    if not text:
        return {}
    value = text.strip()
    if value.startswith("```"):
        value = value.strip("`").strip()
        if value.lower().startswith("json"):
            value = value[4:].strip()
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def propose_analysis_plan(message: str, adata, decision: RouteDecision) -> dict:
    """Return an untrusted LLM proposal. Empty means deterministic fallback."""
    if decision.workflow_id not in _METHOD_FOR_WORKFLOW or not os.getenv("GEMINI_API_KEY"):
        return {}
    profile = adata.uns.get("dataset_profile") or {}
    groups = {
        str(item.get("column")): [str(v) for v in item.get("values") or []]
        for item in profile.get("group_columns") or []
    }
    context = {
        "available_cell_types": _available_cell_types(adata),
        "biological_sample_column": profile.get("sample_column"),
        "available_groups": groups,
        "available_sample_level_covariates": _sample_level_covariates(adata, profile),
        "user_configured_covariates": list(profile.get("deseq2_covariates") or []),
        "routed_workflow": decision.workflow_id,
        "routed_arguments": _route_args(decision),
    }
    instruction = {
        "method": "pseudobulk_deseq2 or sample_level_senescence_score_test",
        "cell_type": "exact available value",
        "unit_of_replication": "exact biological sample column",
        "group_column": "exact grouping column",
        "reference_group": "exact group value",
        "comparison_group": "exact group value",
        "covariates": ["scientifically justified sample-level columns"],
        "excluded_covariates": {"column": "reason"},
        "rationale": "brief scientific rationale",
        "expected_limitations": ["brief limitation"],
    }
    prompt = (
        "Propose a statistical analysis plan for the user request. Return JSON only. "
        "Never treat cells as biological replicates. Use only values in DATASET_CONTEXT. "
        "Preserve every user_configured_covariate unless it is invalid, and explain exclusions.\n"
        f"SCHEMA={json.dumps(instruction)}\n"
        f"DATASET_CONTEXT={json.dumps(context, default=str)}\n"
        f"USER_REQUEST={message!r}"
    )
    try:
        from agent.rate_limit import throttle
        throttle()
        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0, response_mime_type="application/json",
            ),
        )
        return _parse_json(response.text)
    except Exception as exc:
        return {"_planner_error": str(exc)}


def validate_analysis_plan(proposal: dict, adata, decision: RouteDecision) -> dict:
    """Validate a proposal and return the exact executable plan plus audit."""
    profile = adata.uns.get("dataset_profile") or {}
    baseline = _baseline_plan(decision, profile)
    errors: list[str] = []
    warnings: list[str] = []
    if not proposal or proposal.get("_planner_error"):
        if proposal.get("_planner_error"):
            warnings.append(f"planner_unavailable: {proposal['_planner_error']}")
        else:
            warnings.append("planner_unavailable: no LLM proposal was produced")
        return {
            "status": "deterministic_fallback",
            "proposal": proposal,
            "validated_plan": baseline,
            "corrections": [],
            "warnings": warnings,
        }

    expected_method = _METHOD_FOR_WORKFLOW.get(decision.workflow_id or "")
    if proposal.get("method") != expected_method:
        errors.append(f"method must be {expected_method!r} for this routed question")

    available_ct = set(_available_cell_types(adata))
    if proposal.get("cell_type") not in available_ct:
        errors.append("cell_type is not an exact value in the dataset")
    elif baseline.get("cell_type") and proposal.get("cell_type") != baseline.get("cell_type"):
        errors.append("cell_type cannot change the user's validated routed population")

    sample = profile.get("sample_column")
    if proposal.get("unit_of_replication") != sample:
        errors.append(f"unit_of_replication must be the validated sample column {sample!r}")

    group = proposal.get("group_column")
    group_values = {
        str(item.get("column")): {str(v) for v in item.get("values") or []}
        for item in profile.get("group_columns") or []
    }
    if group not in group_values:
        errors.append("group_column is not an available grouping variable")
    else:
        ref, comp = str(proposal.get("reference_group")), str(proposal.get("comparison_group"))
        if ref == comp or ref not in group_values[group] or comp not in group_values[group]:
            errors.append("reference_group and comparison_group must be distinct dataset values")
    routed_contrast = (
        baseline.get("group_column"), str(baseline.get("reference_group")),
        str(baseline.get("comparison_group")),
    )
    proposed_contrast = (
        group, str(proposal.get("reference_group")), str(proposal.get("comparison_group")),
    )
    if all(value not in (None, "None") for value in routed_contrast) and proposed_contrast != routed_contrast:
        errors.append("contrast cannot change the user's validated routed question")

    allowed_covariates = set(_sample_level_covariates(adata, profile))
    proposed_covariates = list(dict.fromkeys(proposal.get("covariates") or []))
    invalid_covariates = [c for c in proposed_covariates if c not in allowed_covariates]
    if invalid_covariates:
        errors.append(f"covariates are not valid sample-level options: {invalid_covariates}")
    configured = list(profile.get("deseq2_covariates") or [])
    missing_configured = [c for c in configured if c not in proposed_covariates]
    if missing_configured:
        errors.append(f"proposal silently removed user-configured covariates: {missing_configured}")

    if errors:
        return {
            "status": "corrected_to_deterministic",
            "proposal": proposal,
            "validated_plan": baseline,
            "corrections": errors,
            "warnings": warnings,
        }

    validated = {
        "method": expected_method,
        "cell_type": proposal["cell_type"],
        "unit_of_replication": proposal["unit_of_replication"],
        "group_column": group,
        "reference_group": str(proposal["reference_group"]),
        "comparison_group": str(proposal["comparison_group"]),
        "covariates": proposed_covariates,
        "excluded_covariates": dict(proposal.get("excluded_covariates") or {}),
        "rationale": str(proposal.get("rationale") or ""),
        "expected_limitations": list(proposal.get("expected_limitations") or []),
    }
    return {
        "status": "accepted",
        "proposal": proposal,
        "validated_plan": validated,
        "corrections": [],
        "warnings": warnings,
    }


def apply_validated_plan(decision: RouteDecision, audit: dict) -> RouteDecision:
    """Convert the validated plan to tool arguments used by the workflow."""
    plan = audit.get("validated_plan") or {}
    tool = _tool_for_workflow(decision.workflow_id or "")
    if not tool:
        return decision
    if decision.workflow_id == "deseq2":
        args = {
            "cell_type": plan.get("cell_type"),
            "sample_column": plan.get("unit_of_replication"),
            "group_column": plan.get("group_column"),
            "reference_group": plan.get("reference_group"),
            "comparison_group": plan.get("comparison_group"),
            "covariates": list(plan.get("covariates") or []),
        }
    else:
        args = {
            "cell_type": plan.get("cell_type"),
            "sample_column": plan.get("unit_of_replication"),
            "age_column": plan.get("group_column"),
            "reference_age": plan.get("reference_group"),
            "comparison_age": plan.get("comparison_group"),
            "covariates": list(plan.get("covariates") or []),
        }
    return RouteDecision(
        workflow_id=decision.workflow_id,
        tool_args={tool: args},
        concept_reply=decision.concept_reply,
        reply_suffix=decision.reply_suffix,
    )


def plan_route(message: str, adata, decision: RouteDecision) -> tuple[RouteDecision, dict | None]:
    if decision.workflow_id not in _METHOD_FOR_WORKFLOW:
        return decision, None
    proposal = propose_analysis_plan(message, adata, decision)
    audit = validate_analysis_plan(proposal, adata, decision)
    return apply_validated_plan(decision, audit), audit
