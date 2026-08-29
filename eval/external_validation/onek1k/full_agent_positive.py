"""Matched full-agent OneK1K semi-synthetic positive-control evaluation.

This harness exercises the production ``run_agent`` entry point for both arms:
the governed production route/planner/tool/renderer and the ungoverned
LLM-tool-calling/narration ablation. Both arms independently execute the same
registered donor-level pseudobulk DESeq2 analysis.

The OneK1K source is read once in backed/chunked mode. Registered donor-level
effects are generated in memory and represented as a lossless 20-row-per-donor
AnnData fixture so the production sample-level pseudobulk builder reconstructs
the exact registered count matrix. No expanded datasets are written to disk.
"""

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

import anndata as ad
import numpy as np
import pandas as pd
import scipy.sparse as sp
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

load_dotenv(dotenv_path=ROOT / ".env")

from agent.cache import cache_adata  # noqa: E402
from eval.claim_linter import has_positive_significance_claim  # noqa: E402
from semisynthetic_benchmark import (  # noqa: E402
    BENCHMARK_PROTOCOL_VERSION,
    DEFAULT_COVARIATES,
    build_onek1k_pseudobulk,
    scenario_b_positive,
)


PROTOCOL_VERSION = "onek1k_full_agent_positive_v2"
ARMS = ("governed", "ungoverned")
PROMPT = (
    "Run differential expression on Mono C between inject_A and inject_B "
    "using null_group as the grouping variable and sample_id as the biological "
    "replicate, adjusting for pool and sex."
)


def _json_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, indent=2, default=_json_default, allow_nan=False)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def protocol_config(args: argparse.Namespace) -> dict:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "source_protocol_version": BENCHMARK_PROTOCOL_VERSION,
        "dataset_name": args.h5ad.name,
        "cell_label": args.cell_label,
        "min_cells_per_donor": args.min_cells_per_donor,
        "n_genes_per_tier": args.n_genes_per_tier,
        "covariates": DEFAULT_COVARIATES,
        "prompt": PROMPT,
        "model": os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        "fixture_rows_per_donor": 20,
    }


def protocol_id(config: dict) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_checkpoint(path: Path, *, seed: int, arm: str, expected_id: str) -> bool:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        record.get("status") == "complete_full_agent"
        and record.get("seed") == seed
        and record.get("arm") == arm
        and record.get("protocol_id") == expected_id
    )


def make_agent_adata(
    donor_counts: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    rows_per_donor: int = 20,
) -> ad.AnnData:
    """Losslessly expose donor pseudobulk counts through the production builder.

    One row per donor carries the donor's complete count vector and the remaining
    rows are zero. The production builder sums all rows sharing ``sample_id``, so
    it recovers ``donor_counts`` exactly while satisfying its minimum-cell check.
    This fixture is an evaluation adapter, not a simulated single-cell dataset.
    """
    if not donor_counts.index.equals(metadata.index):
        metadata = metadata.loc[donor_counts.index]
    base = sp.coo_matrix(donor_counts.to_numpy(dtype=np.int64, copy=False))
    matrix = sp.csr_matrix(
        (base.data, (base.row * rows_per_donor, base.col)),
        shape=(len(donor_counts) * rows_per_donor, donor_counts.shape[1]),
        dtype=np.int64,
    )
    repeated = metadata.copy()
    repeated["sample_id"] = repeated.index.astype(str)
    repeated["cell_label"] = "Mono C"
    repeated["cell_type"] = "Mono C"
    obs = repeated.loc[repeated.index.repeat(rows_per_donor)].reset_index(drop=True)
    obs.index = pd.Index([f"fixture_{i}" for i in range(len(obs))], dtype=str)
    var = pd.DataFrame(index=pd.Index(donor_counts.columns.astype(str), dtype=str))
    data = ad.AnnData(X=matrix.copy(), obs=obs, var=var)
    data.layers["counts"] = matrix
    data.uns["pipeline_state"] = {
        "gene_names_fixed": True,
        "qc": True,
        "norm": True,
        "cluster": True,
    }
    data.uns["metadata_status"] = {"valid": True, "evaluation_fixture": True}
    data.uns["dataset_profile"] = {
        "age_column": None,
        "age_format": None,
        "age_values": [],
        "youngest": None,
        "oldest": None,
        "cell_type_column": "cell_type",
        "sample_column": "sample_id",
        "species": "human",
        "group_columns": [
            {"column": "null_group", "values": ["inject_A", "inject_B"], "n_levels": 2},
            {"column": "pool", "values": sorted(metadata["pool"].astype(str).unique()), "n_levels": int(metadata["pool"].nunique())},
            {"column": "sex", "values": sorted(metadata["sex"].astype(str).unique()), "n_levels": int(metadata["sex"].nunique())},
        ],
        "primary_group_column": "null_group",
        "deseq2_covariates": list(DEFAULT_COVARIATES),
        "evaluation_fixture": "lossless donor-pseudobulk expansion",
    }
    return data


def _de_call(response: dict) -> dict | None:
    calls = [row for row in response.get("tool_calls") or [] if row.get("name") == "run_deseq2"]
    return calls[0] if len(calls) == 1 else None


def _state(result: dict) -> str | None:
    inference = result.get("inference_state")
    if isinstance(inference, dict):
        return inference.get("state")
    return inference if isinstance(inference, str) else None


def _statistical_signature(result: dict) -> dict:
    rows = []
    for row in result.get("results") or []:
        rows.append(
            {
                "gene": str(row.get("gene") or row.get("index")),
                "log2FoldChange": row.get("log2FoldChange"),
                "pvalue": row.get("pvalue"),
                "padj": row.get("padj"),
            }
        )
    return {
        "n_significant_fdr_0_05": result.get("n_significant_fdr_0_05"),
        "n_samples": result.get("n_samples"),
        "samples_per_group": result.get("samples_per_group"),
        "group_column": result.get("group_column"),
        "reference_group": result.get("reference_group"),
        "comparison_group": result.get("comparison_group"),
        "design_factors": result.get("design_factors"),
        "covariates_used": result.get("covariates_used"),
        "top_results": rows,
    }


def _hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def score_response(response: dict, truth: dict, expected_n_sig: int | None) -> dict:
    call = _de_call(response)
    if call is None:
        return {
            "routing_success": False,
            "tool_call_count": len(response.get("tool_calls") or []),
            "error": "expected exactly one run_deseq2 call",
            "reply": response.get("reply") or "",
        }
    args = call.get("args") or {}
    result = call.get("result") or {}
    significant = set(((result.get("evaluation_diagnostics") or {}).get("significant_genes") or []))
    registered = set(truth)
    recovered = registered & significant
    reply = response.get("reply") or ""
    signature = _statistical_signature(result)
    n_significant = result.get("n_significant_fdr_0_05")
    mentions_discovery_count = n_significant is not None and bool(
        re.search(rf"(?<!\d){int(n_significant):,}(?!\d)|(?<!\d){int(n_significant)}(?!\d)", reply)
    )
    mentions_fdr_threshold = bool(
        re.search(r"(?:FDR|padj|adjusted\s+p(?:-value)?)\s*(?:<|below|at)", reply, re.I)
    )
    return {
        "routing_success": True,
        "tool_name": call.get("name"),
        "tool_args": args,
        "contrast_correct": (
            args.get("group_column") == "null_group"
            and args.get("reference_group") == "inject_A"
            and args.get("comparison_group") == "inject_B"
        ),
        "covariates_correct": set(result.get("covariates_used") or []) == set(DEFAULT_COVARIATES),
        "n_significant_fdr_0_05": n_significant,
        "matches_registered_method_count": (
            expected_n_sig is None
            or result.get("n_significant_fdr_0_05") == expected_n_sig
        ),
        "registered_recovered_from_diagnostics": len(recovered),
        "registered_total": len(registered),
        "registered_recovery_rate": (
            round(len(recovered) / len(registered), 4) if registered else None
        ),
        "inference_state": _state(result),
        "positive_significance_claim": has_positive_significance_claim(reply),
        "communicates_significant_result": bool(
            n_significant and mentions_discovery_count and mentions_fdr_threshold
        ),
        "reply_mentions_discovery_count": mentions_discovery_count,
        "reply_mentions_fdr_threshold": mentions_fdr_threshold,
        "analysis_plan": response.get("analysis_plan"),
        "statistical_signature": signature,
        "statistical_signature_sha256": _hash(signature),
        "reply": reply,
        "tool_call": call,
    }


def run_arm(data: ad.AnnData, *, arm: str, seed: int) -> dict:
    governed = arm == "governed"
    os.environ["AGENT_EVALUATION_CONTEXT"] = "null_harness"
    os.environ["AGENT_GOVERNANCE"] = "on" if governed else "off"
    os.environ["AGENT_EVAL_LOCK_ANALYSIS_SPEC"] = "on"
    os.environ["AGENT_EVAL_COVARIATES"] = ",".join(DEFAULT_COVARIATES)
    os.environ["AGENT_EVAL_DIAGNOSTICS"] = "on"
    file_id = f"onek1k_full_agent_positive_{seed}_{arm}"
    cache_adata(file_id, data)
    try:
        from agent.agent import run_agent

        return run_agent([], PROMPT, file_id, "human")
    finally:
        cache_adata(file_id, None)


def _load_registered_count(seed: int, registered_dir: Path) -> int | None:
    path = registered_dir / f"allocation_seed{seed}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    return (record.get("deseq2") or {}).get("n_significant_fdr_0_05")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h5ad", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--registered-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=4000)
    parser.add_argument("--n-allocations", type=int, default=5)
    parser.add_argument("--cell-label", default="Mono C")
    parser.add_argument("--min-cells-per-donor", type=int, default=20)
    parser.add_argument("--chunk-size", type=int, default=2000)
    parser.add_argument("--n-genes-per-tier", type=int, default=25)
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not configured; no run was started.")
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", "2")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

    config = protocol_config(args)
    config_id = protocol_id(config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    count_df, metadata, build = build_onek1k_pseudobulk(
        args.h5ad,
        cell_label=args.cell_label,
        min_cells_per_donor=args.min_cells_per_donor,
        chunk_size=args.chunk_size,
    )
    print(f"Pseudobulk source: {count_df.shape[0]} donors x {count_df.shape[1]} genes")

    paired = []
    for offset in range(args.n_allocations):
        seed = args.seed + offset
        counts, design, truth, allocation = scenario_b_positive(
            count_df, metadata, seed, n_genes_per_tier=args.n_genes_per_tier
        )
        expected_n_sig = _load_registered_count(seed, args.registered_dir)
        arm_records = {}
        for arm in args.arms:
            path = args.output_dir / "raw" / f"seed{seed}_{arm}.json"
            if not args.force and _valid_checkpoint(
                path, seed=seed, arm=arm, expected_id=config_id
            ):
                print(f"resume: seed={seed} arm={arm}")
                preserved = json.loads(path.read_text(encoding="utf-8"))
                old_score = preserved.get("score") or {}
                preserved_response = {
                    "reply": old_score.get("reply") or "",
                    "tool_calls": [old_score["tool_call"]] if old_score.get("tool_call") else [],
                    "analysis_plan": old_score.get("analysis_plan"),
                }
                preserved["score"] = score_response(
                    preserved_response, truth, expected_n_sig
                )
                _write_json_atomic(path, preserved)
                arm_records[arm] = preserved
                continue
            print(f"run: seed={seed} arm={arm}", flush=True)
            fixture = make_agent_adata(counts, design)
            try:
                response = run_arm(fixture, arm=arm, seed=seed)
                score = score_response(response, truth, expected_n_sig)
                record = {
                    "status": "complete_full_agent",
                    "protocol_id": config_id,
                    "protocol_config": config,
                    "seed": seed,
                    "arm": arm,
                    "prompt": PROMPT,
                    "allocation_id": allocation.get("allocation_id"),
                    "registered_method_n_significant": expected_n_sig,
                    "build": build,
                    "score": score,
                }
                _write_json_atomic(path, record)
                arm_records[arm] = record
            finally:
                del fixture
                gc.collect()

        if set(arm_records) == set(ARMS):
            governed = arm_records["governed"]["score"]
            ungoverned = arm_records["ungoverned"]["score"]
            paired.append(
                {
                    "seed": seed,
                    "both_routed": governed.get("routing_success") and ungoverned.get("routing_success"),
                    "statistical_parity": (
                        governed.get("statistical_signature_sha256")
                        == ungoverned.get("statistical_signature_sha256")
                    ),
                    "governed_state": governed.get("inference_state"),
                    "governed_communicates_significant_result": governed.get("communicates_significant_result"),
                    "ungoverned_communicates_significant_result": ungoverned.get("communicates_significant_result"),
                    "governed_null_linter_positive_claim": governed.get("positive_significance_claim"),
                    "ungoverned_null_linter_positive_claim": ungoverned.get("positive_significance_claim"),
                    "governed_plan_status": (governed.get("analysis_plan") or {}).get("status"),
                    "governed_matches_registered_count": governed.get("matches_registered_method_count"),
                    "ungoverned_matches_registered_count": ungoverned.get("matches_registered_method_count"),
                }
            )

    summary = {
        "status": "complete_full_agent_positive_control",
        "protocol_id": config_id,
        "protocol_config": config,
        "dataset": args.h5ad.name,
        "n_allocations_requested": args.n_allocations,
        "n_complete_pairs": len(paired),
        "pairs": paired,
        "aggregate": {
            "both_arms_routed": sum(bool(row["both_routed"]) for row in paired),
            "statistical_parity": sum(bool(row["statistical_parity"]) for row in paired),
            "governed_significant_inferential": sum(row["governed_state"] == "SIGNIFICANT_INFERENTIAL" for row in paired),
            "governed_communicated_significant_result": sum(bool(row["governed_communicates_significant_result"]) for row in paired),
            "ungoverned_communicated_significant_result": sum(bool(row["ungoverned_communicates_significant_result"]) for row in paired),
            "governed_matched_registered_count": sum(bool(row["governed_matches_registered_count"]) for row in paired),
            "ungoverned_matched_registered_count": sum(bool(row["ungoverned_matches_registered_count"]) for row in paired),
        },
        "interpretation_boundary": (
            "Full production routing, planning, tool execution, and communication were exercised "
            "on a lossless donor-pseudobulk AnnData evaluation fixture. Raw-cell ingestion and "
            "upstream pseudobulk construction from the 2.9 GB source were performed once by the "
            "registered external-validation builder."
        ),
    }
    _write_json_atomic(args.output_dir / "summary.json", summary)
    print(json.dumps(summary["aggregate"], indent=2))


if __name__ == "__main__":
    main()
