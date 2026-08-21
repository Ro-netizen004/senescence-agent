"""Assemble validated n=1 ungoverned shards into canonical paired sweep files."""

from __future__ import annotations

import json
from collections import Counter

from agent_null_sweep import _rate, aggregate_diagnostics, score_confounding_design
from run_paired_ungoverned_shards import (
    CONFIGS,
    OUT,
    _governed_path,
    _load_valid_shard,
    _parity_error,
    _shard_path,
    _slug,
)


def _canonical_path(tissue: str, cell_type: str):
    return OUT / (
        f"agent_null_{tissue}_{_slug(cell_type)}_ungoverned_same_method_"
        "stratified_valid_ordinary_seed2000_n30.json"
    )


def _metric(rows: list[dict], field: str):
    successes = sum(bool(row.get(field)) for row in rows)
    return _rate(successes, len(rows))


def assemble_one(tissue: str, cell_type: str):
    governed_payload = json.loads(_governed_path(tissue, cell_type).read_text(encoding="utf-8"))
    governed_rows = [
        row for row in governed_payload["permutations"]
        if not row.get("skipped") and not row.get("agent_error")
    ]
    rows = []
    for governed in governed_rows:
        seed = int(governed["seed"])
        shard_path = _shard_path(tissue, cell_type, seed)
        if not _load_valid_shard(shard_path, governed):
            raise ValueError(f"Missing or invalid shard: {tissue} seed {seed}")
        shard = json.loads(shard_path.read_text(encoding="utf-8"))
        row = shard["permutations"][0]
        mismatch = _parity_error(governed, row)
        if mismatch:
            raise ValueError(f"Parity failure: {tissue} seed {seed} field {mismatch}")
        rows.append(row)

    seeds = [int(row["seed"]) for row in rows]
    if len(seeds) != len(set(seeds)):
        raise ValueError(f"Duplicate assembled seeds for {tissue}")

    sig_rows = [row for row in rows if row.get("ran_deseq2")]
    licensed_rows = [row for row in sig_rows if row.get("inference_state") is not None]
    raw_rate, raw_ci = _metric(sig_rows, "raw_discovery")
    licensed_rate, licensed_ci = _metric(licensed_rows, "licensed_claim")
    reply_rate, reply_ci = _metric(rows, "reply_overclaim")
    withheld_rate, withheld_ci = _metric(sig_rows, "result_withheld")
    plausibility_rate, plausibility_ci = _metric(sig_rows, "plausibility_withheld")
    stability_rate, stability_ci = _metric(sig_rows, "stability_withheld")
    exploratory_rate, exploratory_ci = _metric(sig_rows, "exploratory_fp")
    mean_discoveries = (
        round(sum(row["n_sig"] for row in sig_rows) / len(sig_rows), 2)
        if sig_rows else None
    )

    summary = {
        "dataset": governed_payload["dataset"],
        "cell_type": governed_payload["cell_type"],
        "arm": "ungoverned_same_method",
        "mode": governed_payload["mode"],
        "design": governed_payload["design"],
        "prompt_style": governed_payload["prompt_style"],
        "prompt": governed_payload["prompt"],
        "null_group_column": governed_payload["null_group_column"],
        "null_groups": governed_payload["null_groups"],
        "n_perm_requested": governed_payload["n_perm_requested"],
        "n_perm_completed": len(rows),
        "n_perm_ran_deseq2": len(sig_rows),
        "n_perm_agent_errors": 0,
        "n_perm_blocked": sum(bool(row.get("blocked")) for row in rows),
        "n_perm_routing_miss": sum(
            row.get("error") == "run_deseq2 not called (routing miss)" for row in rows
        ),
        "n_duplicate_allocations_skipped": governed_payload["n_duplicate_allocations_skipped"],
        "inference_state_counts": dict(sorted(Counter(
            row.get("inference_state") or ("BLOCKED" if row.get("blocked") else "UNKNOWN")
            for row in rows
        ).items())),
        "mean_null_discoveries": mean_discoveries,
        "mean_fp_genes": mean_discoveries,
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
        "false_discovery_rate": licensed_rate,
        "exploratory_fp_rate": exploratory_rate,
        "confounding_evaluation": score_confounding_design(governed_payload["design"], rows),
        "diagnostics": aggregate_diagnostics(sig_rows),
        "truth": governed_payload["truth"],
        "assembly": {
            "source": "validated per-seed n1 shards",
            "paired_against": _governed_path(tissue, cell_type).name,
            "parity_fields": [
                "allocation_id", "n_sig", "significant_genes", "design_factors",
                "covariates_used", "covariates_dropped",
            ],
        },
        "permutations": rows,
    }
    output = _canonical_path(tissue, cell_type)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return output, len(rows)


def main():
    total = 0
    for tissue, cell_type in CONFIGS:
        path, count = assemble_one(tissue, cell_type)
        total += count
        print(f"ASSEMBLED {tissue}: {count} -> {path}")
    print(f"DONE assembled={total}")


if __name__ == "__main__":
    main()
