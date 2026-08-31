"""Matched full-agent rerun of the registered OneK1K constructed nulls."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(HERE)]
load_dotenv(dotenv_path=ROOT / ".env")

from agent.cache import cache_adata  # noqa: E402
from eval.claim_linter import has_positive_significance_claim  # noqa: E402
from build_pseudobulk import build_onek1k_pseudobulk, paired_null_allocation  # noqa: E402
from full_agent_positive import (  # noqa: E402
    _de_call,
    _hash,
    _statistical_signature,
    make_agent_adata,
)


PROTOCOL_VERSION = "onek1k_full_agent_null_v1"
ARMS = ("governed", "ungoverned")
COVARIATES = ["pool", "sex", "age"]
PROMPT = (
    "Run differential expression on Mono C between fake_A and fake_B using "
    "null_group as the grouping variable and sample_id as the biological "
    "replicate, adjusting for pool, sex, and age."
)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, indent=2, allow_nan=False, default=str)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def protocol_config(args: argparse.Namespace) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "dataset_name": args.h5ad.name,
        "cell_label": args.cell_label,
        "min_cells_per_donor": args.min_cells_per_donor,
        "covariates": COVARIATES,
        "prompt": PROMPT,
        "model": os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        "seed_start": args.seed,
        "n_allocations": args.n_allocations,
        "fixture_rows_per_donor": 20,
    }


def protocol_id(config: dict) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_checkpoint(path: Path, seed: int, arm: str, expected_id: str) -> bool:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        record.get("status") == "complete_full_agent_null"
        and record.get("seed") == seed
        and record.get("arm") == arm
        and record.get("protocol_id") == expected_id
    )


def make_null_agent_adata(counts, metadata):
    data = make_agent_adata(counts, metadata)
    profile = data.uns["dataset_profile"]
    profile["group_columns"][0] = {
        "column": "null_group",
        "values": ["fake_A", "fake_B"],
        "n_levels": 2,
    }
    profile["deseq2_covariates"] = list(COVARIATES)
    return data


def score_response(response: dict, registered: dict) -> dict:
    call = _de_call(response)
    if call is None:
        return {
            "routing_success": False,
            "error": "expected exactly one run_deseq2 call",
            "reply": response.get("reply") or "",
        }
    args = call.get("args") or {}
    result = call.get("result") or {}
    reply = response.get("reply") or ""
    n_sig = result.get("n_significant_fdr_0_05")
    signature = _statistical_signature(result)
    communicates_null = bool(
        n_sig == 0
        and re.search(
            r"(?:0|no)\s+(?:statistically\s+)?significant"
            r"|no\s+genes?.{0,40}(?:significant|passed|met)"
            r"|significant[^\n:]{0,60}:\s*0(?:\s+genes?)?"
            r"|significant[^\n]{0,100}\b0\s*$",
            reply,
            re.I | re.M,
        )
        and not has_positive_significance_claim(reply)
    )
    inference = result.get("inference_state")
    state = inference.get("state") if isinstance(inference, dict) else inference
    return {
        "routing_success": True,
        "tool_args": args,
        "contrast_correct": (
            args.get("group_column") == "null_group"
            and args.get("reference_group") == "fake_A"
            and args.get("comparison_group") == "fake_B"
        ),
        "covariates_correct": set(result.get("covariates_used") or []) == set(COVARIATES),
        "allocation_id_matches_registered": registered["allocation_id"] is not None,
        "n_significant_fdr_0_05": n_sig,
        "matches_registered_discovery_count": n_sig == registered["n_discoveries"],
        "inference_state": state,
        "positive_significance_claim": has_positive_significance_claim(reply),
        "communicates_no_significant_result": communicates_null,
        "analysis_plan": response.get("analysis_plan"),
        "statistical_signature": signature,
        "statistical_signature_sha256": _hash(signature),
        "reply": reply,
        "tool_call": call,
    }


def run_arm(data, arm: str, seed: int) -> dict:
    governed = arm == "governed"
    os.environ["AGENT_EVALUATION_CONTEXT"] = "null_harness"
    os.environ["AGENT_GOVERNANCE"] = "on" if governed else "off"
    os.environ["AGENT_EVAL_LOCK_ANALYSIS_SPEC"] = "on"
    os.environ["AGENT_EVAL_COVARIATES"] = ",".join(COVARIATES)
    os.environ["AGENT_EVAL_DIAGNOSTICS"] = "on"
    file_id = f"onek1k_full_agent_null_{seed}_{arm}"
    cache_adata(file_id, data)
    try:
        from agent.agent import run_agent

        return run_agent([], PROMPT, file_id, "human")
    finally:
        cache_adata(file_id, None)


def load_registered(directory: Path, seed: int) -> dict:
    record = json.loads((directory / f"seed{seed}" / "summary.json").read_text(encoding="utf-8"))
    return {
        "allocation_id": (record.get("allocation") or {}).get("allocation_id"),
        "n_discoveries": int(record["n_null_discoveries_fdr_0_05"]),
        "n_genes_tested": int(record["n_genes_tested"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h5ad", type=Path, required=True)
    parser.add_argument("--registered-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=3000)
    parser.add_argument("--n-allocations", type=int, default=10)
    parser.add_argument("--cell-label", default="Mono C")
    parser.add_argument("--min-cells-per-donor", type=int, default=20)
    parser.add_argument("--chunk-size", type=int, default=2000)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not configured; no run was started.")
    for key, value in {
        "LOKY_MAX_CPU_COUNT": "2",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }.items():
        os.environ.setdefault(key, value)

    config = protocol_config(args)
    config_id = protocol_id(config)
    count_df, metadata, build = build_onek1k_pseudobulk(
        args.h5ad,
        cell_label=args.cell_label,
        min_cells_per_donor=args.min_cells_per_donor,
        chunk_size=args.chunk_size,
    )
    print(f"Pseudobulk source: {count_df.shape[0]} donors x {count_df.shape[1]} genes")
    pairs = []
    for offset in range(args.n_allocations):
        seed = args.seed + offset
        registered = load_registered(args.registered_dir, seed)
        design, allocation = paired_null_allocation(metadata.reset_index(), seed)
        if allocation.get("allocation_id") != registered["allocation_id"]:
            raise ValueError(f"Registered allocation mismatch at seed {seed}")
        counts = count_df.loc[design.index].copy()
        arm_records = {}
        for arm in args.arms:
            path = args.output_dir / "raw" / f"seed{seed}_{arm}.json"
            if not args.force and _valid_checkpoint(path, seed, arm, config_id):
                print(f"resume: seed={seed} arm={arm}")
                preserved = json.loads(path.read_text(encoding="utf-8"))
                old_score = preserved.get("score") or {}
                response = {
                    "reply": old_score.get("reply") or "",
                    "tool_calls": [old_score["tool_call"]] if old_score.get("tool_call") else [],
                    "analysis_plan": old_score.get("analysis_plan"),
                }
                preserved["score"] = score_response(response, registered)
                _write_json_atomic(path, preserved)
                arm_records[arm] = preserved
                continue
            print(f"run: seed={seed} arm={arm}", flush=True)
            fixture = make_null_agent_adata(counts, design)
            try:
                response = run_arm(fixture, arm, seed)
                record = {
                    "status": "complete_full_agent_null",
                    "protocol_id": config_id,
                    "protocol_config": config,
                    "seed": seed,
                    "arm": arm,
                    "prompt": PROMPT,
                    "allocation_id": allocation["allocation_id"],
                    "registered": registered,
                    "build": build,
                    "score": score_response(response, registered),
                }
                _write_json_atomic(path, record)
                arm_records[arm] = record
            finally:
                del fixture
                gc.collect()
        if set(arm_records) == set(ARMS):
            g, u = arm_records["governed"]["score"], arm_records["ungoverned"]["score"]
            pairs.append(
                {
                    "seed": seed,
                    "both_routed": g.get("routing_success") and u.get("routing_success"),
                    "statistical_parity": g.get("statistical_signature_sha256") == u.get("statistical_signature_sha256"),
                    "both_match_registered": g.get("matches_registered_discovery_count") and u.get("matches_registered_discovery_count"),
                    "governed_state": g.get("inference_state"),
                    "governed_communicates_null": g.get("communicates_no_significant_result"),
                    "ungoverned_communicates_null": u.get("communicates_no_significant_result"),
                    "governed_positive_claim": g.get("positive_significance_claim"),
                    "ungoverned_positive_claim": u.get("positive_significance_claim"),
                    "governed_plan_status": (g.get("analysis_plan") or {}).get("status"),
                }
            )
    summary = {
        "status": "complete_full_agent_null",
        "protocol_id": config_id,
        "protocol_config": config,
        "dataset": args.h5ad.name,
        "n_complete_pairs": len(pairs),
        "pairs": pairs,
        "aggregate": {
            "both_arms_routed": sum(bool(x["both_routed"]) for x in pairs),
            "statistical_parity": sum(bool(x["statistical_parity"]) for x in pairs),
            "both_matched_registered": sum(bool(x["both_match_registered"]) for x in pairs),
            "governed_not_significant": sum(x["governed_state"] == "NOT_SIGNIFICANT" for x in pairs),
            "governed_communicated_null": sum(bool(x["governed_communicates_null"]) for x in pairs),
            "ungoverned_communicated_null": sum(bool(x["ungoverned_communicates_null"]) for x in pairs),
            "governed_positive_claims": sum(bool(x["governed_positive_claim"]) for x in pairs),
            "ungoverned_positive_claims": sum(bool(x["ungoverned_positive_claim"]) for x in pairs),
            "governed_plans_accepted": sum(x["governed_plan_status"] == "accepted" for x in pairs),
        },
        "interpretation_boundary": (
            "This is a full-agent routing/execution/communication null validation, but zero "
            "discoveries in every registered allocation prevent estimation of a governance "
            "withholding effect. The ten allocations reuse one donor cohort."
        ),
    }
    _write_json_atomic(args.output_dir / "summary.json", summary)
    print(json.dumps(summary["aggregate"], indent=2))


if __name__ == "__main__":
    main()
