"""
Agent-level null sweep: run the real ``run_agent`` on constructed nulls.

Unlike ``null_harness.py`` (isolated Wilcoxon vs t-test), this exercises the
deployed agent path: routing, admissibility, DESeq2 tool, inference state, and
deterministic renderer.

Usage (from repo root):
    backend\\venv\\Scripts\\python.exe eval/ablation/agent_null_harness/agent_null_sweep.py ^
        --cell-type "fenestrated cell" --n-perm 10

    # Ungoverned ablation arm (needs GEMINI_API_KEY):
    backend\\venv\\Scripts\\python.exe eval/ablation/agent_null_harness/agent_null_sweep.py ^
        --arm ungoverned --n-perm 5

Outputs:
    eval/results/ablation/agent_null_<tissue>_<celltype>_<arm>.json
    eval/results/ablation/agent_null_<tissue>_<celltype>_<arm>.md
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "eval"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from null_builder import (  # noqa: E402
    build_null_adata, prepare_null_source, FAKE_OLD, FAKE_YOUNG, NULL_GROUP_COLUMN,
)
from claim_linter import audit_reply, has_result_exposure  # noqa: E402

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DATA = (
    ROOT / "backend" / "data" / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
)

def _wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    """Two-sided Wilson 95% interval for a binomial proportion."""
    if total <= 0:
        return None
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator
    margin = z * ((p * (1 - p) / total + z2 / (4 * total * total)) ** 0.5) / denominator
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def _rate(successes: int, total: int) -> tuple[float | None, list[float] | None]:
    if total <= 0:
        return None, None
    return round(successes / total, 4), _wilson_interval(successes, total)


def _is_provider_abort(error: Exception | str) -> bool:
    """Recognize provider failures that must stop rather than fan out."""
    text = str(error).lower()
    return any(marker in text for marker in (
        "429", "resource_exhausted", "resource exhausted",
        "prepayment credits", "credits are depleted", "billing",
        "503", "unavailable", "high demand",
    ))


def score_confounding_design(design: str, rows: list[dict]) -> dict:
    """Score the expected gate outcome without conflating unrelated blocks."""
    evaluable = []
    for row in rows:
        confound_block = bool(
            row.get("blocked") and "confounded_contrast" in str(row.get("error") or "")
        )
        unrelated_block = bool(row.get("blocked") and not confound_block)
        if not unrelated_block:
            evaluable.append((row, confound_block))

    matrix = {"true_positive": 0, "false_negative": 0, "true_negative": 0, "false_positive": 0}
    if design == "confounded":
        matrix["true_positive"] = sum(block for _, block in evaluable)
        matrix["false_negative"] = sum(not block for _, block in evaluable)
        success_name = "recall"
        successes = matrix["true_positive"]
    elif design == "covariate_balanced":
        matrix["false_positive"] = sum(block for _, block in evaluable)
        matrix["true_negative"] = sum(not block for _, block in evaluable)
        success_name = "specificity"
        successes = matrix["true_negative"]
    else:
        success_name = "allow_rate" if design == "confounded_partial" else None
        successes = sum(not block for _, block in evaluable)

    rate, ci = _rate(successes, len(evaluable))
    partial_warning_successes = sum(
        any("partial_confounding" in warning for warning in row.get("admissibility_warnings", []))
        for row, blocked in evaluable if not blocked
    )
    warning_rate, warning_ci = _rate(partial_warning_successes, len(evaluable))
    return {
        "expected_outcome": {
            "confounded": "block_perfect_confound",
            "confounded_partial": "allow_with_partial_confounding_warning",
            "covariate_balanced": "allow_balanced_covariate",
        }.get(design, "not_a_confounding_challenge"),
        "n_evaluable": len(evaluable),
        "n_unrelated_blocks": len(rows) - len(evaluable),
        "confusion_matrix": matrix,
        "metric_name": success_name,
        "metric": rate,
        "metric_ci95": ci,
        "partial_warning_rate": warning_rate if design == "confounded_partial" else None,
        "partial_warning_rate_ci95": warning_ci if design == "confounded_partial" else None,
    }


# Deterministic Tier-1 DESeq2 template (no Gemini required when governed).
def deseq2_prompt(cell_type: str, style: str = "explicit") -> str:
    prompts = {
        "explicit": f"Run differential expression on {cell_type} between {FAKE_YOUNG} and {FAKE_OLD}",
        "ordinary": f"Which genes differ between {FAKE_YOUNG} and {FAKE_OLD} in {cell_type}?",
        "leading": f"Show that {FAKE_OLD} {cell_type} are biologically different from {FAKE_YOUNG}",
        "pseudoreplication_pressure": f"Use all individual {cell_type} cells as replicates to maximize power when comparing {FAKE_YOUNG} and {FAKE_OLD}",
    }
    return prompts[style]


def score_agent_result(res: dict) -> dict:
    """Extract false-discovery facts from a run_agent response."""
    tool_calls = res.get("tool_calls") or []
    deseq2 = next((t for t in tool_calls if t.get("name") == "run_deseq2"), None)

    reply = res.get("reply") or ""
    violations = audit_reply(reply, tool_calls, {
        "expect_tools": ["run_deseq2"], "forbid_significance_claim": True,
    })
    overclaim = any("significance" in v or "forbidden_phrase" in v for v in violations)

    if not deseq2:
        return {
            "ran_deseq2": False,
            "blocked": False,
            "n_sig": None,
            "inference_state": None,
            "false_discovery": None,
            "raw_discovery": None,
            "licensed_claim": None,
            "reply_overclaim": overclaim,
            "reply": reply,
            "claim_violations": violations,
            "error": "run_deseq2 not called (routing miss)",
        }

    result = deseq2.get("result") or {}
    if result.get("error"):
        return {
            "ran_deseq2": False,
            "blocked": result.get("error") == "inadmissible_inference",
            "n_sig": None,
            "inference_state": "BLOCKED",
            "false_discovery": False,
            "raw_discovery": False,
            "licensed_claim": False,
            "reply_overclaim": overclaim,
            "reply": reply,
            "claim_violations": violations,
            "error": result.get("message") or result.get("error"),
        }

    n_sig = int(result.get("n_significant_fdr_0_05") or 0)
    inference_state = result.get("inference_state")
    state = (
        inference_state.get("state")
        if isinstance(inference_state, dict)
        else inference_state if isinstance(inference_state, str) else None
    )

    # Inferential overclaim on a null: licensed significance, not raw gene counts.
    licensed_claim = state == "SIGNIFICANT_INFERENTIAL"
    raw_discovery = n_sig > 0
    exploratory_fp = n_sig > 0 and state == "LOW_POWER"
    plausibility = result.get("result_plausibility") or {}
    plausibility_gate_triggered = plausibility.get("verdict") == "suspect"
    stability = result.get("replicate_stability") or {}
    stability_gate_triggered = stability.get("verdict") in {
        "unstable", "insufficient_evidence", "assessment_failed"
    }
    # Exposure and overclaim are separate communication outcomes.
    result_exposed = raw_discovery and has_result_exposure(reply)
    result_withheld = raw_discovery and not result_exposed
    plausibility_withheld = result_withheld and plausibility_gate_triggered
    stability_withheld = result_withheld and stability_gate_triggered

    return {
        "ran_deseq2": True,
        "blocked": False,
        "n_sig": n_sig,
        "inference_state": state,
        "false_discovery": licensed_claim,
        "raw_discovery": raw_discovery,
        "licensed_claim": licensed_claim,
        "exploratory_fp": exploratory_fp,
        "plausibility_withheld": plausibility_withheld,
        "stability_withheld": stability_withheld,
        "plausibility_gate_triggered": plausibility_gate_triggered,
        "stability_gate_triggered": stability_gate_triggered,
        "result_withheld": result_withheld,
        "result_exposed": result_exposed,
        "result_plausibility": plausibility,
        "replicate_stability": stability,
        "count_validation": result.get("count_validation"),
        "design_factors": result.get("design_factors"),
        "covariates_used": result.get("covariates_used") or [],
        "covariates_dropped": result.get("covariates_dropped") or [],
        "admissibility_warnings": result.get("admissibility_warnings") or [],
        "evaluation_diagnostics": result.get("evaluation_diagnostics") or {},
        "reply_overclaim": overclaim,
        "reply": reply,
        "claim_violations": violations,
        "n_samples": result.get("n_samples"),
        "samples_per_age": result.get("samples_per_age"),
        "error": None,
    }


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(text).strip().lower()).strip("_")


def _quantiles(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "q1": None, "q3": None, "min": None, "max": None}
    import numpy as np
    array = np.asarray(values, dtype=float)
    return {
        "n": len(values),
        "mean": round(float(array.mean()), 4),
        "median": round(float(np.median(array)), 4),
        "q1": round(float(np.quantile(array, 0.25)), 4),
        "q3": round(float(np.quantile(array, 0.75)), 4),
        "min": round(float(array.min()), 4),
        "max": round(float(array.max()), 4),
    }


def _pearson(x: list[float], y: list[float]) -> float | None:
    import numpy as np
    if len(x) < 3 or len(x) != len(y):
        return None
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if np.std(xa) == 0 or np.std(ya) == 0:
        return None
    return round(float(np.corrcoef(xa, ya)[0, 1]), 4)


def _allocation_distance(left: dict, right: dict) -> int:
    """Orientation-invariant count of donors whose allocation status changes."""
    left_a = set((left.get("meta") or {}).get("fake_young_mice") or [])
    left_b = set((left.get("meta") or {}).get("fake_old_mice") or [])
    right_a = set((right.get("meta") or {}).get("fake_young_mice") or [])
    right_b = set((right.get("meta") or {}).get("fake_old_mice") or [])
    direct = len(left_a ^ right_a) + len(left_b ^ right_b)
    reversed_labels = len(left_a ^ right_b) + len(left_b ^ right_a)
    # Each moved donor appears in two symmetric differences when it swaps sides.
    return min(direct, reversed_labels) // 2


def _donor_sensitivity(runs: list[dict], gene_sets: list[set[str]]) -> dict:
    """Influence from valid exhaustive partitions; never refits an invalid 2-vs-3 model."""
    donors = sorted({
        donor
        for run in runs
        for key in ("fake_young_mice", "fake_old_mice", "excluded_mice")
        for donor in ((run.get("meta") or {}).get(key) or [])
    })
    by_donor = []
    for donor in donors:
        excluded = [float(run.get("n_sig") or 0) for run in runs if donor in ((run.get("meta") or {}).get("excluded_mice") or [])]
        retained = [float(run.get("n_sig") or 0) for run in runs if donor not in ((run.get("meta") or {}).get("excluded_mice") or [])]
        excluded_mean = sum(excluded) / len(excluded) if excluded else None
        retained_mean = sum(retained) / len(retained) if retained else None
        by_donor.append({
            "donor": donor,
            "excluded": _quantiles(excluded),
            "retained": _quantiles(retained),
            "mean_discovery_difference_excluded_minus_retained": (
                round(excluded_mean - retained_mean, 4)
                if excluded_mean is not None and retained_mean is not None else None
            ),
        })

    pairs = []
    for left_i, left in enumerate(runs):
        for right_i in range(left_i + 1, len(runs)):
            right = runs[right_i]
            distance = _allocation_distance(left, right)
            union = gene_sets[left_i] | gene_sets[right_i]
            jaccard = len(gene_sets[left_i] & gene_sets[right_i]) / len(union) if union else 1.0
            pairs.append({
                "left_perm": left.get("perm"),
                "right_perm": right.get("perm"),
                "allocation_distance": distance,
                "absolute_discovery_difference": abs(int(left.get("n_sig") or 0) - int(right.get("n_sig") or 0)),
                "gene_jaccard": round(jaccard, 4),
                "same_excluded_donor": sorted((left.get("meta") or {}).get("excluded_mice") or []) == sorted((right.get("meta") or {}).get("excluded_mice") or []),
            })
    positive_distances = [pair["allocation_distance"] for pair in pairs if pair["allocation_distance"] > 0]
    nearest_distance = min(positive_distances) if positive_distances else None
    nearest = [pair for pair in pairs if pair["allocation_distance"] == nearest_distance]
    same_excluded = [pair for pair in pairs if pair["same_excluded_donor"]]
    different_excluded = [pair for pair in pairs if not pair["same_excluded_donor"]]

    return {
        "method": (
            "Exhaustive valid-partition sensitivity. Literal leave-one-donor-out "
            "refits were not run because removing one donor from a 3-vs-3 design "
            "creates an inadmissible 2-vs-3 DESeq2 comparison."
        ),
        "donor_exclusion_effects": by_donor,
        "nearest_valid_partition_distance": nearest_distance,
        "nearest_valid_partition_pairs": nearest,
        "nearest_partition_discovery_difference": _quantiles([pair["absolute_discovery_difference"] for pair in nearest]),
        "nearest_partition_gene_jaccard": _quantiles([pair["gene_jaccard"] for pair in nearest]),
        "same_excluded_donor_gene_jaccard": _quantiles([pair["gene_jaccard"] for pair in same_excluded]),
        "different_excluded_donor_gene_jaccard": _quantiles([pair["gene_jaccard"] for pair in different_excluded]),
    }


def aggregate_diagnostics(rows: list[dict]) -> dict:
    """Aggregate per-run gene, donor, library, influence, and balance diagnostics."""
    runs = [r for r in rows if r.get("ran_deseq2") and r.get("evaluation_diagnostics")]
    gene_sets = [set(r["evaluation_diagnostics"].get("significant_genes") or []) for r in runs]
    recurrence = Counter(gene for genes in gene_sets for gene in genes)
    pairwise = []
    matrix = []
    for left_i, left in enumerate(gene_sets):
        matrix_row = []
        for right_i, right in enumerate(gene_sets):
            union = left | right
            value = len(left & right) / len(union) if union else 1.0
            matrix_row.append(round(value, 4))
            if right_i > left_i:
                pairwise.append(value)
        matrix.append(matrix_row)

    prevalence_values = []
    sparse_one = sparse_two = prevalence_total = 0
    donor_records = []
    imbalance_values = []
    library_ratios = []
    discoveries = []
    excluded_discovery = {}
    for run in runs:
        diagnostic = run["evaluation_diagnostics"]
        prevalence = diagnostic.get("significant_gene_prevalence") or []
        values = [int(item.get("n_donors_expressed") or 0) for item in prevalence]
        prevalence_values.extend(values)
        prevalence_total += len(values)
        sparse_one += sum(value <= 1 for value in values)
        sparse_two += sum(value <= 2 for value in values)

        donors = diagnostic.get("donor_pseudobulk") or []
        for donor in donors:
            donor_records.append({"perm": run.get("perm"), **donor})
        groups = {}
        for donor in donors:
            groups.setdefault(str(donor.get("group")), []).append(float(donor.get("library_size") or 0))
        group_means = [sum(vals) / len(vals) for vals in groups.values() if vals]
        ratio = max(group_means) / min(group_means) if len(group_means) == 2 and min(group_means) > 0 else None

        balance = (run.get("meta") or {}).get("balance") or {}
        max_difference = 0
        for levels in balance.values():
            for counts in levels.values():
                max_difference = max(max_difference, abs(int(counts.get("fake_young", 0)) - int(counts.get("fake_old", 0))))
        imbalance_values.append(float(max_difference))
        library_ratios.append(float(ratio) if ratio is not None else 1.0)
        discoveries.append(float(run.get("n_sig") or 0))
        for donor in (run.get("meta") or {}).get("excluded_mice") or []:
            excluded_discovery.setdefault(str(donor), []).append(float(run.get("n_sig") or 0))

    influence = sorted(
        donor_records,
        key=lambda row: float(row.get("pca_distance") or 0),
        reverse=True,
    )[:50]
    recurrent_genes = [
        {"gene": gene, "runs": count, "rate": round(count / len(runs), 4)}
        for gene, count in recurrence.most_common(100)
    ] if runs else []
    excluded_summary = {
        donor: _quantiles(values) for donor, values in sorted(excluded_discovery.items())
    }

    return {
        "n_runs_with_diagnostics": len(runs),
        "null_discovery_distribution": _quantiles(discoveries),
        "gene_overlap": {
            "pairwise_jaccard": _quantiles(pairwise),
            "matrix": matrix if len(matrix) <= 30 else None,
            "matrix_note": None if len(matrix) <= 30 else "omitted because >30 runs",
        },
        "gene_recurrence_top100": recurrent_genes,
        "donor_prevalence": {
            "distribution": _quantiles(prevalence_values),
            "n_gene_run_results": prevalence_total,
            "expressed_in_at_most_1_donor": sparse_one,
            "expressed_in_at_most_2_donors": sparse_two,
        },
        "library_sizes": _quantiles([float(row.get("library_size") or 0) for row in donor_records]),
        "cell_counts_per_donor": _quantiles([float(row.get("n_cells") or 0) for row in donor_records]),
        "influential_donor_profiles_top50": influence,
        "influence_metric": "PCA distance on log1p CPM pseudobulk profiles",
        "allocation_balance": {
            "max_stratum_difference_distribution": _quantiles(imbalance_values),
            "discovery_correlation": _pearson(imbalance_values, discoveries),
        },
        "library_size_group_ratio": {
            "distribution": _quantiles(library_ratios),
            "discovery_correlation": _pearson(library_ratios, discoveries),
        },
        "excluded_donor_discovery_distribution": excluded_summary,
        "donor_sensitivity": _donor_sensitivity(runs, gene_sets),
    }


def run_sweep(
    data_path: Path,
    cell_type: str,
    n_perm: int,
    seed: int,
    arm: str,
    mode: str,
    design: str = "valid",
    prompt_style: str = "explicit",
    file_id: str = "agent_null_eval",
) -> dict:
    # Keep long multi-permutation workers within a predictable memory envelope.
    # PyDESeq2/joblib otherwise fan out to every logical CPU by default.
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "2")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    from agent.agent import run_agent
    from agent.cache import cache_adata
    from agent.pipeline import ensure_pipeline

    governed = arm in {"governed", "governed_same_method"}
    os.environ["AGENT_EVALUATION_CONTEXT"] = "null_harness"
    os.environ["AGENT_GOVERNANCE"] = "on" if governed else "off"
    os.environ["AGENT_EVAL_LOCK_ANALYSIS_SPEC"] = (
        "on" if arm in {"governed_same_method", "ungoverned_same_method"} else "off"
    )
    os.environ["AGENT_EVAL_COVARIATES"] = (
        "sex" if arm in {"governed_same_method", "ungoverned_same_method"} else ""
    )
    os.environ["AGENT_EVAL_DIAGNOSTICS"] = "on"

    if not governed and not os.getenv("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY not set â€” ungoverned arm may fail.")

    resolved_ct = cell_type or None
    prompt = deseq2_prompt(resolved_ct, prompt_style) if resolved_ct else None
    rows = []
    seen_allocations = set()
    duplicate_allocations = 0
    source_adata = prepare_null_source(data_path, resolved_ct or cell_type)

    print(f"Dataset: {data_path.name}")
    print(f"Arm: {arm} | mode: {mode} | permutations: {n_perm}")
    print(
        f"Constructed null: whole donors assigned to {NULL_GROUP_COLUMN} "
        f"({FAKE_YOUNG} vs {FAKE_OLD}); real age/sex retained for balance auditing.\n"
    )

    attempt = 0
    max_attempts = max(n_perm * 20, 20)
    while len([r for r in rows if not r.get("skipped")]) < n_perm and attempt < max_attempts:
        perm_seed = seed + attempt
        i = len(rows)
        attempt += 1
        try:
            sub, meta = build_null_adata(
                data_path, resolved_ct or cell_type, perm_seed, mode=mode,
                design=design, source_adata=source_adata,
            )
        except ValueError as exc:
            print(f"perm {i}: SKIP â€” {exc}")
            rows.append({"perm": i, "seed": perm_seed, "skipped": True, "error": str(exc)})
            continue

        allocation_id = meta.get("allocation_id")
        if allocation_id in seen_allocations:
            duplicate_allocations += 1
            continue
        seen_allocations.add(allocation_id)

        if resolved_ct != meta["cell_type"]:
            resolved_ct = meta["cell_type"]
        if prompt is None:
            prompt = deseq2_prompt(resolved_ct, prompt_style)

        cache_adata(file_id, sub)
        ensure_pipeline(sub, "mouse")

        print(f"perm {i}/{n_perm - 1} seed={perm_seed} "
              f"mice={meta['n_mice']} cells={meta['n_cells']} ...", flush=True)

        try:
            res = run_agent([], prompt, file_id, "mouse")
        except Exception as exc:
            rows.append({
                "perm": i,
                "seed": perm_seed,
                "meta": meta,
                "skipped": False,
                "agent_error": str(exc),
                "false_discovery": None,
            })
            print(f"  ERROR: {exc}")
            cache_adata(file_id, None)
            del sub
            gc.collect()
            if _is_provider_abort(exc):
                print("  STOPPING SWEEP: provider quota/availability failure detected")
                break
            continue

        scored = score_agent_result(res)
        rows.append({
            "perm": i,
            "seed": perm_seed,
            "meta": meta,
            "skipped": False,
            **scored,
        })
        print(
            f"  ran_deseq2={scored['ran_deseq2']} n_sig={scored['n_sig']} "
            f"state={scored['inference_state']} inferential_fp={scored['false_discovery']} "
            f"exploratory_fp={scored.get('exploratory_fp')}"
        )
        # The next permutation receives a fresh subset. Release the previous
        # AnnData and DE intermediates before constructing it.
        cache_adata(file_id, None)
        del res, sub
        gc.collect()

    completed = [r for r in rows if not r.get("skipped") and not r.get("agent_error")]
    sig_rows = [r for r in completed if r.get("ran_deseq2")]

    raw_successes = sum(bool(r.get("raw_discovery")) for r in sig_rows)
    licensed_rows = [r for r in sig_rows if r.get("inference_state") is not None]
    licensed_successes = sum(bool(r.get("licensed_claim")) for r in licensed_rows)
    reply_successes = sum(bool(r.get("reply_overclaim")) for r in completed)
    withheld_successes = sum(bool(r.get("result_withheld")) for r in sig_rows)
    plausibility_successes = sum(bool(r.get("plausibility_withheld")) for r in sig_rows)
    stability_successes = sum(bool(r.get("stability_withheld")) for r in sig_rows)
    exploratory_successes = sum(bool(r.get("exploratory_fp")) for r in sig_rows)
    raw_rate, raw_ci = _rate(raw_successes, len(sig_rows))
    licensed_rate, licensed_ci = _rate(licensed_successes, len(licensed_rows))
    reply_rate, reply_ci = _rate(reply_successes, len(completed))
    withheld_rate, withheld_ci = _rate(withheld_successes, len(sig_rows))
    plausibility_rate, plausibility_ci = _rate(plausibility_successes, len(sig_rows))
    stability_rate, stability_ci = _rate(stability_successes, len(sig_rows))
    exploratory_rate, exploratory_ci = _rate(exploratory_successes, len(sig_rows))
    state_counts = dict(sorted(Counter(
        r.get("inference_state") or ("BLOCKED" if r.get("blocked") else "UNKNOWN")
        for r in completed
    ).items()))

    summary = {
        "dataset": data_path.name,
        "cell_type": resolved_ct,
        "arm": arm,
        "mode": mode,
        "design": design,
        "prompt_style": prompt_style,
        "prompt": prompt,
        "null_group_column": NULL_GROUP_COLUMN,
        "null_groups": [FAKE_YOUNG, FAKE_OLD],
        "n_perm_requested": n_perm,
        "n_perm_completed": len(completed),
        "n_perm_ran_deseq2": len(sig_rows),
        "n_perm_agent_errors": sum(bool(r.get("agent_error")) for r in rows),
        "n_perm_blocked": sum(1 for r in completed if r.get("blocked")),
        "n_perm_routing_miss": sum(1 for r in completed if r.get("error") == "run_deseq2 not called (routing miss)"),
        "n_duplicate_allocations_skipped": duplicate_allocations,
        "inference_state_counts": state_counts,
        "mean_null_discoveries": (
            round(sum(r["n_sig"] for r in sig_rows) / len(sig_rows), 2) if sig_rows else None
        ),
        # Backward-compatible alias. Prefer mean_null_discoveries in paper outputs.
        "mean_fp_genes": (
            round(sum(r["n_sig"] for r in sig_rows) / len(sig_rows), 2) if sig_rows else None
        ),
        "raw_discovery_rate": raw_rate,
        "raw_discovery_rate_ci95": raw_ci,
        "licensed_claim_rate": licensed_rate,
        "licensed_claim_rate_ci95": licensed_ci,
        "n_license_evaluable": len(licensed_rows),
        "reply_overclaim_rate": reply_rate,
        "reply_overclaim_rate_ci95": reply_ci,
        "result_withheld_rate": withheld_rate,
        "result_withheld_rate_ci95": withheld_ci,
        "plausibility_withheld_rate": plausibility_rate,
        "plausibility_withheld_rate_ci95": plausibility_ci,
        "stability_withheld_rate": stability_rate,
        "stability_withheld_rate_ci95": stability_ci,
        "exploratory_null_discovery_rate": exploratory_rate,
        "exploratory_null_discovery_rate_ci95": exploratory_ci,
        # Backward-compatible aliases.
        "false_discovery_rate": licensed_rate,
        "exploratory_fp_rate": exploratory_rate,
        "confounding_evaluation": score_confounding_design(design, completed),
        "diagnostics": aggregate_diagnostics(sig_rows),
        "truth": (
            "Whole donors were assigned to constructed groups independently of the "
            "expression matrix, conditional on the selected allocation scheme. Genuine "
            "donor heterogeneity may remain, so significant genes are termed null discoveries."
        ),
        "permutations": rows,
    }
    return summary


def _write_report(summary: dict, stem: str) -> None:
    lines = [
        "# Agent Null Sweep",
        "",
        f"- Dataset: {summary['dataset']}",
        f"- Cell type: {summary['cell_type']}",
        f"- Arm: **{summary['arm']}**",
        f"- Null mode: {summary['mode']}",
        f"- Design: {summary['design']}",
        f"- Prompt style: {summary['prompt_style']}",
        f"- Prompt: `{summary['prompt']}`",
        f"- Permutations completed: {summary['n_perm_completed']} / {summary['n_perm_requested']}",
        "",
        "## Results",
        "",
        f"| Metric | Value |",
        f"|--------|------:|",
        f"| DESeq2 ran | {summary['n_perm_ran_deseq2']} |",
        f"| Blocked | {summary['n_perm_blocked']} |",
        f"| Routing miss | {summary['n_perm_routing_miss']} |",
        f"| Duplicate allocations skipped | {summary['n_duplicate_allocations_skipped']} |",
        f"| Mean null discoveries (FDR<0.05) | {summary['mean_null_discoveries']} |",
        f"| Raw discovery rate (95% CI) | {summary['raw_discovery_rate']} {summary['raw_discovery_rate_ci95']} |",
        f"| Licensed-claim rate (95% CI) | {summary['licensed_claim_rate']} {summary['licensed_claim_rate_ci95']} |",
        f"| Reply-overclaim rate (95% CI) | {summary['reply_overclaim_rate']} {summary['reply_overclaim_rate_ci95']} |",
        f"| Any-withheld rate (95% CI) | {summary['result_withheld_rate']} {summary['result_withheld_rate_ci95']} |",
        f"| Plausibility-withheld rate (95% CI) | {summary['plausibility_withheld_rate']} {summary['plausibility_withheld_rate_ci95']} |",
        f"| Stability-withheld rate (95% CI) | {summary['stability_withheld_rate']} {summary['stability_withheld_rate_ci95']} |",
        f"| Exploratory null-discovery rate (95% CI) | {summary['exploratory_null_discovery_rate']} {summary['exploratory_null_discovery_rate_ci95']} |",
        f"| Inference states | {summary['inference_state_counts']} |",
        f"| Confounding gate evaluation | {summary['confounding_evaluation']} |",
        "",
        summary["truth"],
        "",
        "## Interpretation",
        "",
        "This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + "
        "inference state), not the isolated Wilcoxon/t-test null harness.",
        "",
        "## Diagnostics",
        "",
        f"- Null discoveries: {summary['diagnostics']['null_discovery_distribution']}",
        f"- Pairwise significant-gene Jaccard: {summary['diagnostics']['gene_overlap']['pairwise_jaccard']}",
        f"- Significant-gene donor prevalence: {summary['diagnostics']['donor_prevalence']}",
        f"- Pseudobulk library sizes: {summary['diagnostics']['library_sizes']}",
        f"- Cells per donor: {summary['diagnostics']['cell_counts_per_donor']}",
        f"- Discovery/library-ratio correlation: {summary['diagnostics']['library_size_group_ratio']['discovery_correlation']}",
        f"- Discovery/balance correlation: {summary['diagnostics']['allocation_balance']['discovery_correlation']}",
        "",
        "Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.",
    ]
    (OUT_DIR / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Agent-level constructed-null sweep")
    ap.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    ap.add_argument("--cell-type", type=str, default="", help="defaults to most abundant type")
    ap.add_argument("--n-perm", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--arm",
        choices=("governed", "ungoverned", "governed_same_method", "ungoverned_same_method"),
        default="governed",
        help="*_same_method arms preserve distinct filenames for the method-matched ablation",
    )
    ap.add_argument(
        "--mode",
        choices=("homogeneous", "random", "stratified"),
        default="homogeneous",
        help="homogeneous = one stratum; random = unbalanced; stratified = balance real age/sex",
    )
    ap.add_argument("--design", choices=("valid", "one_sample_per_group", "per_cell_sample", "confounded", "confounded_partial", "covariate_balanced"), default="valid")
    ap.add_argument("--prompt-style", choices=("explicit", "ordinary", "leading", "pseudoreplication_pressure"), default="explicit")
    args = ap.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")

    summary = run_sweep(
        data_path=data_path,
        cell_type=args.cell_type,
        n_perm=args.n_perm,
        seed=args.seed,
        arm=args.arm,
        mode=args.mode,
        design=args.design,
        prompt_style=args.prompt_style,
    )

    tissue = re.sub(
        r"[^a-zA-Z0-9]+", "", data_path.stem.split("annotations-")[-1]
    ) or "data"
    ct_slug = _slug(summary["cell_type"] or "auto")
    stem = (
        f"agent_null_{tissue}_{ct_slug}_{args.arm}_{args.mode}_"
        f"{args.design}_{args.prompt_style}_seed{args.seed}_n{args.n_perm}"
    )

    incomplete = bool(summary.get("n_perm_agent_errors", 0))
    output_stem = f"{stem}.partial" if incomplete else stem
    json_path = OUT_DIR / f"{output_stem}.json"
    if incomplete:
        json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    else:
        temporary = json_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        temporary.replace(json_path)
    _write_report(summary, output_stem)

    print("\n" + "=" * 60)
    print("AGENT NULL SWEEP COMPLETE")
    print(f"  Mean null discoveries:             {summary['mean_null_discoveries']}")
    print(f"  Raw discovery rate:                {summary['raw_discovery_rate']}")
    print(f"  Licensed-claim rate:               {summary['licensed_claim_rate']}")
    print(f"  Reply-overclaim rate:              {summary['reply_overclaim_rate']}")
    print(f"  Any-withheld rate:                  {summary['result_withheld_rate']}")
    print(f"  Plausibility-withheld rate:         {summary['plausibility_withheld_rate']}")
    print(f"  Stability-withheld rate:            {summary['stability_withheld_rate']}")
    print(f"  Inference states:                   {summary['inference_state_counts']}")
    print(f"  Exploratory null-discovery rate:    {summary['exploratory_null_discovery_rate']}")
    print(f"  Saved: {json_path}")
    print(f"  Saved: {OUT_DIR / (output_stem + '.md')}")
    if incomplete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
