"""Resumable OneK1K semi-synthetic validity-firewall benchmark.

Scenarios use real classical-monocyte donor pseudobulk counts:

  A. Clean paired donor-split null: admissibility should allow; no signal added.
  B. Registered positive: 75 donor-level effects across three log2FC tiers;
     admissibility should allow and governance should license stable signal.
  C. Pool-confounded contrast: production admissibility should block before DE.

No LLM calls are made. Counts are constructed once in memory with the validated
backed/chunked OneK1K builder. Every scenario/allocation is atomically
checkpointed and skipped on resume unless ``--force`` is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(HERE))

from agent.admissibility import check_admissibility  # noqa: E402
from agent.inference_state import apply_inference_state  # noqa: E402
from tools.run_deseq2 import (  # noqa: E402
    assess_de_plausibility,
    assess_replicate_stability,
    run_deseq2_pseudobulk,
)

from build_pseudobulk import (  # noqa: E402
    build_onek1k_pseudobulk,
    paired_null_allocation,
)

REGISTERED_LOG2FC_TIERS = (0.25, 0.50, 1.00)
DEFAULT_GENES_PER_TIER = 25
DEFAULT_COVARIATES = ["pool", "sex"]
BENCHMARK_PROTOCOL_VERSION = "onek1k_semisynthetic_v2"


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
    """Return the analysis-defining configuration used to validate resumes."""
    return {
        "protocol_version": BENCHMARK_PROTOCOL_VERSION,
        "dataset_name": args.h5ad.name,
        "cell_label": args.cell_label,
        "min_cells_per_donor": args.min_cells_per_donor,
        "registered_log2fc_tiers": list(REGISTERED_LOG2FC_TIERS),
        "n_genes_per_tier": args.n_genes_per_tier,
        "covariates": DEFAULT_COVARIATES,
    }


def protocol_id(config: dict) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _valid_checkpoint(path: Path, scenario: str, seed: int, expected_protocol_id: str) -> bool:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        record.get("status") == "complete_no_llm_calls"
        and record.get("scenario") == scenario
        and record.get("seed") == seed
        and record.get("protocol_id") == expected_protocol_id
    )


def _paired_groups(metadata: pd.DataFrame, seed: int, prefix: str) -> tuple[pd.DataFrame, dict]:
    allocated, diagnostics = paired_null_allocation(metadata.reset_index(), seed)
    rename = {"fake_A": f"{prefix}_A", "fake_B": f"{prefix}_B"}
    allocated = allocated.copy()
    allocated["null_group"] = allocated["null_group"].map(rename)
    diagnostics = dict(diagnostics)
    diagnostics["groups"] = [f"{prefix}_A", f"{prefix}_B"]
    return allocated, diagnostics


def scenario_a_null(count_df: pd.DataFrame, metadata: pd.DataFrame, seed: int):
    """Age-adjacent pool/sex-paired allocation with no injected effect."""
    allocated, allocation = _paired_groups(metadata, seed, "null")
    return count_df.loc[allocated.index].copy(), allocated, {}, allocation


def select_registered_genes(
    count_df: pd.DataFrame,
    *,
    seed: int,
    n_genes_per_tier: int = DEFAULT_GENES_PER_TIER,
) -> list[str]:
    """Select reproducible, donor-prevalent genes away from count extremes."""
    prevalence = count_df.gt(0).mean(axis=0)
    means = count_df.mean(axis=0)
    prevalent = means[(prevalence >= 0.90) & (means > 0)]
    required = n_genes_per_tier * len(REGISTERED_LOG2FC_TIERS)
    if len(prevalent) < required:
        raise ValueError("Too few genes expressed in at least 90% of eligible donors")
    lower, upper = prevalent.quantile([0.25, 0.90])
    candidates = prevalent[(prevalent >= lower) & (prevalent <= upper)].index.astype(str)
    if len(candidates) < required:
        raise ValueError(f"Only {len(candidates)} moderate-count genes; need {required}")
    rng = np.random.default_rng(seed)
    return rng.choice(np.sort(candidates), size=required, replace=False).tolist()


def scenario_b_positive(
    count_df: pd.DataFrame,
    metadata: pd.DataFrame,
    seed: int,
    n_genes_per_tier: int = DEFAULT_GENES_PER_TIER,
):
    """Inject balanced donor-level up/down effects into registered genes."""
    allocated, allocation = _paired_groups(metadata, seed, "inject")
    counts = count_df.loc[allocated.index].copy()
    selected = select_registered_genes(counts, seed=seed, n_genes_per_tier=n_genes_per_tier)
    group_b = allocated.index[allocated["null_group"] == "inject_B"]
    truth: dict[str, dict] = {}
    offset = 0
    for log2fc in REGISTERED_LOG2FC_TIERS:
        genes = selected[offset : offset + n_genes_per_tier]
        offset += n_genes_per_tier
        for position, gene in enumerate(genes):
            sign = 1 if (position + int(log2fc * 100)) % 2 == 0 else -1
            factor = 2.0 ** (sign * log2fc)
            original = counts.loc[group_b, gene].to_numpy(dtype=float)
            counts.loc[group_b, gene] = np.maximum(
                np.rint(original * factor).astype(np.int64), 0
            )
            truth[gene] = {
                "injected_log2fc": float(sign * log2fc),
                "absolute_log2fc_tier": float(log2fc),
                "direction": "up_in_B" if sign > 0 else "down_in_B",
            }
    allocation["registered_genes"] = len(truth)
    allocation["direction_counts"] = {
        "up_in_B": sum(v["direction"] == "up_in_B" for v in truth.values()),
        "down_in_B": sum(v["direction"] == "down_in_B" for v in truth.values()),
    }
    return counts, allocated, truth, allocation


def scenario_c_confounded(count_df: pd.DataFrame, metadata: pd.DataFrame, seed: int):
    """Align groups exactly with the two largest pools."""
    pool_counts = metadata["pool"].astype(str).value_counts()
    if len(pool_counts) < 2:
        raise ValueError("Need at least two pools for the confounded scenario")
    pools = pool_counts.index[:2].tolist()
    retained = metadata[metadata["pool"].astype(str).isin(pools)].copy()
    retained["null_group"] = retained["pool"].astype(str).map(
        {pools[0]: "confound_A", pools[1]: "confound_B"}
    )
    truth = {
        "expected_decision": "blocked",
        "confounded_variable": "pool",
        "pool_to_group": {pools[0]: "confound_A", pools[1]: "confound_B"},
    }
    allocation = {
        "seed": seed,
        "groups": ["confound_A", "confound_B"],
        "samples_per_group": retained["null_group"].value_counts().to_dict(),
    }
    return count_df.loc[retained.index].copy(), retained, truth, allocation


def make_gate_adata(metadata: pd.DataFrame, *, cells_per_donor: int = 20):
    """Minimal raw-count AnnData carrying the exact donor-level design."""
    import anndata as ad

    sample_name = metadata.index.name or "index"
    repeated = metadata.reset_index().rename(columns={sample_name: "sample_id"})
    repeated["sample_id"] = repeated["sample_id"].astype(str)
    repeated["cell_label"] = "Mono C"
    obs = repeated.loc[repeated.index.repeat(cells_per_donor)].reset_index(drop=True)
    matrix = sp.csr_matrix(np.ones((len(obs), 1), dtype=np.int64))
    adata = ad.AnnData(X=matrix.copy(), obs=obs, var=pd.DataFrame(index=["gate_gene"]))
    adata.layers["counts"] = matrix
    adata.uns["dataset_profile"] = {
        "sample_column": "sample_id",
        "cell_type_column": "cell_label",
        "primary_group_column": "null_group",
    }
    return adata


def run_production_admissibility(metadata: pd.DataFrame, groups: list[str]) -> dict:
    adata = make_gate_adata(metadata)
    args = {
        "cell_type": "Mono C",
        "cell_type_column": "cell_label",
        "sample_column": "sample_id",
        "group_column": "null_group",
        "reference_group": groups[0],
        "comparison_group": groups[1],
        "covariates": DEFAULT_COVARIATES,
    }
    return check_admissibility("run_deseq2", args, adata)


def _run_deseq2_and_governance(
    count_df: pd.DataFrame, metadata: pd.DataFrame, groups: list[str], truth: dict
) -> dict:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_deseq2_pseudobulk(
            count_df,
            metadata,
            group_column="null_group",
            reference_group=groups[0],
            comparison_group=groups[1],
            covariates=DEFAULT_COVARIATES,
        )
    table = result["results"]
    significant = table[table["padj"].notna() & table["padj"].lt(0.05)]
    plausibility = assess_de_plausibility(table)
    stability = assess_replicate_stability(
        count_df, metadata, table, "null_group", groups[0], groups[1]
    )
    payload = {
        "results": table.head(100).reset_index().rename(columns={"index": "gene"}).to_dict(orient="records"),
        "n_significant_fdr_0_05": int(len(significant)),
        "n_samples": int(len(metadata)),
        "samples_per_group": {
            str(k): int(v) for k, v in metadata["null_group"].value_counts().items()
        },
        "group_column": "null_group",
        "reference_group": groups[0],
        "comparison_group": groups[1],
        "covariates_used": DEFAULT_COVARIATES,
        "result_plausibility": plausibility,
        "replicate_stability": stability,
    }
    governed = apply_inference_state(
        "run_deseq2",
        payload,
        {
            "cell_type": "Mono C",
            "group_column": "null_group",
            "reference_group": groups[0],
            "comparison_group": groups[1],
            "covariates": DEFAULT_COVARIATES,
        },
    )
    truth_genes = set(truth)
    significant_genes = set(significant.index.astype(str))
    true_positive = truth_genes & significant_genes
    false_positive = significant_genes - truth_genes if truth_genes else significant_genes
    direction_correct = sum(
        np.sign(float(table.loc[g, "log2FoldChange"]))
        == np.sign(float(truth[g]["injected_log2fc"]))
        for g in true_positive
    )
    tier_summary = {}
    for tier in REGISTERED_LOG2FC_TIERS:
        tier_genes = {
            gene for gene, spec in truth.items()
            if spec.get("absolute_log2fc_tier") == tier
        }
        if tier_genes:
            tier_summary[str(tier)] = {
                "registered": len(tier_genes),
                "recovered": len(tier_genes & significant_genes),
                "sensitivity": round(len(tier_genes & significant_genes) / len(tier_genes), 4),
            }
    runtime_warnings = sorted({
        str(item.message) for item in caught if issubclass(item.category, RuntimeWarning)
    })
    return {
        "n_genes_tested": int(len(table)),
        "n_significant_fdr_0_05": int(len(significant)),
        "true_positives": len(true_positive),
        "false_negatives": len(truth_genes - significant_genes),
        "false_positives": len(false_positive),
        "sensitivity": round(len(true_positive) / len(truth_genes), 4) if truth_genes else None,
        "empirical_false_discovery_proportion": (
            round(len(false_positive) / len(significant_genes), 4) if significant_genes else 0.0
        ),
        "direction_agreement_among_recovered": (
            round(direction_correct / len(true_positive), 4) if true_positive else None
        ),
        "tier_summary": tier_summary,
        "plausibility": plausibility,
        "replicate_stability": stability,
        "governed_inference_state": governed["inference_state"],
        "runtime_warnings": runtime_warnings,
        "registered_gene_results": {
            gene: {
                "injected_log2fc": truth[gene]["injected_log2fc"],
                "observed_log2fc": float(table.loc[gene, "log2FoldChange"]),
                "padj": float(table.loc[gene, "padj"]) if pd.notna(table.loc[gene, "padj"]) else None,
            }
            for gene in sorted(truth_genes)
        },
    }


SCENARIOS = {"A": scenario_a_null, "B": scenario_b_positive, "C": scenario_c_confounded}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h5ad", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenarios", nargs="+", default=["A", "B", "C"], choices=SCENARIOS)
    parser.add_argument("--seed", type=int, default=4000)
    parser.add_argument("--n-allocations", type=int, default=5)
    parser.add_argument("--cell-label", default="Mono C")
    parser.add_argument("--min-cells-per-donor", type=int, default=20)
    parser.add_argument("--chunk-size", type=int, default=2000)
    parser.add_argument("--n-genes-per-tier", type=int, default=DEFAULT_GENES_PER_TIER)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config = protocol_config(args)
    config_id = protocol_id(config)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    count_df, metadata, build = build_onek1k_pseudobulk(
        args.h5ad,
        cell_label=args.cell_label,
        min_cells_per_donor=args.min_cells_per_donor,
        chunk_size=args.chunk_size,
    )
    print(f"Pseudobulk: {count_df.shape[0]} eligible donors x {count_df.shape[1]} genes for {args.cell_label}")

    completed = []
    for scenario in args.scenarios:
        for index in range(args.n_allocations):
            seed = args.seed + index
            output = args.output_dir / f"scenario_{scenario}" / f"allocation_seed{seed}.json"
            if not args.force and _valid_checkpoint(output, scenario, seed, config_id):
                print(f"resume: {scenario} seed={seed}")
                completed.append(json.loads(output.read_text(encoding="utf-8")))
                continue
            kwargs = {"n_genes_per_tier": args.n_genes_per_tier} if scenario == "B" else {}
            counts, design, truth, allocation = SCENARIOS[scenario](count_df, metadata, seed, **kwargs)
            groups = allocation["groups"]
            admissibility = run_production_admissibility(design, groups)
            expected_admissible = scenario in {"A", "B"}
            record = {
                "status": "complete_no_llm_calls",
                "scenario": scenario,
                "seed": seed,
                "protocol_id": config_id,
                "protocol_config": config,
                "cell_label": args.cell_label,
                "expected_admissible": expected_admissible,
                "admissibility_expectation_met": admissibility["admissible"] == expected_admissible,
                "admissibility": admissibility,
                "allocation": allocation,
                "truth": truth,
                "build": build,
                "deseq2": None,
            }
            if admissibility["admissible"]:
                record["deseq2"] = _run_deseq2_and_governance(counts, design, groups, truth)
            _write_json_atomic(output, record)
            completed.append(record)
            state = ((record.get("deseq2") or {}).get("governed_inference_state") or {}).get("state")
            print(f"complete: {scenario} seed={seed} admissible={admissibility['admissible']} state={state}")

    aggregate = {
        "status": "complete_no_llm_calls",
        "dataset": str(args.h5ad),
        "cell_label": args.cell_label,
        "protocol_id": config_id,
        "protocol_config": config,
        "scenarios": args.scenarios,
        "n_allocations_requested_per_scenario": args.n_allocations,
        "n_records": len(completed),
        "admissibility_expectations_met": sum(bool(row["admissibility_expectation_met"]) for row in completed),
        "records": [
            {
                "scenario": row["scenario"],
                "seed": row["seed"],
                "admissible": row["admissibility"]["admissible"],
                "admissibility_expectation_met": row["admissibility_expectation_met"],
                "n_significant_fdr_0_05": (row.get("deseq2") or {}).get("n_significant_fdr_0_05"),
                "sensitivity": (row.get("deseq2") or {}).get("sensitivity"),
                "empirical_false_discovery_proportion": (row.get("deseq2") or {}).get("empirical_false_discovery_proportion"),
                "governed_state": (((row.get("deseq2") or {}).get("governed_inference_state") or {}).get("state")),
            }
            for row in completed
        ],
    }
    _write_json_atomic(args.output_dir / "benchmark_summary.json", aggregate)
    print(json.dumps({k: v for k, v in aggregate.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
