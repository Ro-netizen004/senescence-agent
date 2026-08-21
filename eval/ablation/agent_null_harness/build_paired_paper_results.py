"""Build auditable paired paper outputs from completed agent null sweeps."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "eval"))

from claim_linter import audit_reply, has_result_exposure  # noqa: E402


PROTOCOL_DIR = ROOT / "eval/results/final_candidate/null_sweep_same_method"
PROTOCOL = json.loads((PROTOCOL_DIR / "protocol.json").read_text(encoding="utf-8"))
ARMS = tuple(PROTOCOL["paired_arms"])
CONFIGS = [
    (
        row["tissue"],
        "_".join(part for part in row["cell_type"].lower().replace("-", "_").split()),
    )
    for row in PROTOCOL["planned_tissue_cell_types"]
]
MODE = PROTOCOL["null_construction"]["mode"]
DESIGN = PROTOCOL["null_construction"]["design"]
PROMPT_STYLE = PROTOCOL["null_construction"]["prompt_style"]
SEED_START = PROTOCOL["seed_start"]
N_REQUESTED = PROTOCOL["n_requested_per_tissue_arm"]
SEED_SCHEDULE = PROTOCOL["seed_schedule"]
MAX_ATTEMPTS = max(
    N_REQUESTED * SEED_SCHEDULE["max_attempt_multiplier"],
    SEED_SCHEDULE["minimum_max_attempts"],
)
SEEDS = tuple(range(SEED_START, SEED_START + MAX_ATTEMPTS))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [round(max(0, center - half), 4), round(min(1, center + half), 4)]


def _input_path(source: Path, tissue: str, cell_slug: str, arm: str) -> Path:
    return source / (
        f"agent_null_{tissue}_{cell_slug}_{arm}_{MODE}_{DESIGN}_{PROMPT_STYLE}_"
        f"seed{SEED_START}_n{N_REQUESTED}.json"
    )


def _rescore(row: dict) -> tuple[bool, list[str], bool, bool]:
    violations = audit_reply(
        row.get("reply", ""), [], {"forbid_significance_claim": True}
    )
    overclaim = any(
        "significance" in violation or "forbidden_phrase" in violation
        for violation in violations
    )
    exposed = bool(row.get("n_sig", 0)) and has_result_exposure(row.get("reply", ""))
    withheld = bool(row.get("n_sig", 0)) and not exposed
    return overclaim, violations, exposed, withheld


def _index_permutations(payload: dict, *, tissue: str, arm: str) -> dict[int, dict]:
    rows = payload.get("permutations") or []
    seeds = [int(row["seed"]) for row in rows]
    if len(seeds) != len(set(seeds)):
        raise ValueError(f"Duplicate seeds for {tissue} {arm}")
    completed = payload.get("n_perm_completed")
    if completed != len(rows):
        raise ValueError(
            f"Completion-count mismatch for {tissue} {arm}: "
            f"summary={completed}, rows={len(rows)}"
        )
    if not rows:
        raise ValueError(f"No completed permutations for {tissue} {arm}")
    requested = payload.get("n_perm_requested")
    duplicates = payload.get("n_duplicate_allocations_skipped", 0)
    attempts = len(rows) + duplicates
    if requested != N_REQUESTED or completed > requested:
        raise ValueError(
            f"Request-count mismatch for {tissue} {arm}: "
            f"requested={requested}, completed={completed}"
        )
    if completed < requested and attempts != MAX_ATTEMPTS:
        raise ValueError(
            f"Incomplete allocation search for {tissue} {arm}: "
            f"attempts={attempts}, expected exhaustion at {MAX_ATTEMPTS}"
        )
    if completed == requested and attempts > MAX_ATTEMPTS:
        raise ValueError(f"Too many attempts for {tissue} {arm}: {attempts}")
    preregistered_seeds = set(SEEDS)
    if not set(seeds).issubset(preregistered_seeds):
        raise ValueError(f"Non-preregistered seed for {tissue} {arm}")
    expected_metadata = {
        "arm": arm,
        "mode": MODE,
        "design": DESIGN,
        "prompt_style": PROMPT_STYLE,
    }
    for field, expected in expected_metadata.items():
        if payload.get(field) != expected:
            raise ValueError(
                f"Protocol mismatch for {tissue} {arm}: "
                f"{field}={payload.get(field)!r}, expected {expected!r}"
            )
    return {seed: row for seed, row in zip(seeds, rows)}


def build(source: Path, output: Path, copy_raw: bool = True) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / "raw"
    if copy_raw:
        raw_dir.mkdir(parents=True, exist_ok=True)

    pairs = []
    manifest = []
    tissue_rows = []
    for tissue, cell_slug in CONFIGS:
        loaded = {}
        paths = {}
        for arm in ARMS:
            path = _input_path(source, tissue, cell_slug, arm)
            if not path.exists():
                raise FileNotFoundError(path)
            paths[arm] = path
            loaded[arm] = json.loads(path.read_text(encoding="utf-8"))
            copied = raw_dir / path.name
            if copy_raw:
                shutil.copy2(path, copied)
            manifest.append(
                {
                    "file": f"raw/{path.name}",
                    "tissue": tissue,
                    "arm": arm,
                    "completed": loaded[arm]["n_perm_completed"],
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )

        governed_arm, ungoverned_arm = ARMS
        by_arm = {
            arm: _index_permutations(loaded[arm], tissue=tissue, arm=arm)
            for arm in loaded
        }
        if set(by_arm[governed_arm]) != set(by_arm[ungoverned_arm]):
            raise ValueError(f"Unpaired seeds for {tissue}")

        tissue_pairs = []
        for seed in sorted(by_arm[governed_arm]):
            governed = by_arm[governed_arm][seed]
            ungoverned = by_arm[ungoverned_arm][seed]
            g_alloc = (governed.get("meta") or {}).get("allocation_id")
            u_alloc = (ungoverned.get("meta") or {}).get("allocation_id")
            if not g_alloc or g_alloc != u_alloc:
                raise ValueError(f"Allocation mismatch for {tissue} seed {seed}")
            parity_fields = ("n_sig", "design_factors", "covariates_used", "covariates_dropped")
            for field in parity_fields:
                if governed.get(field) != ungoverned.get(field):
                    raise ValueError(
                        f"Method-parity failure for {tissue} seed {seed}: {field} differs"
                    )
            g_genes = set(
                (governed.get("evaluation_diagnostics") or {}).get("significant_genes") or []
            )
            u_genes = set(
                (ungoverned.get("evaluation_diagnostics") or {}).get("significant_genes") or []
            )
            if g_genes != u_genes:
                raise ValueError(
                    f"Method-parity failure for {tissue} seed {seed}: significant genes differ"
                )
            g_overclaim, g_violations, g_exposed, g_withheld = _rescore(governed)
            u_overclaim, u_violations, u_exposed, u_withheld = _rescore(ungoverned)
            pair = {
                "tissue": tissue,
                "cell_type": loaded[governed_arm]["cell_type"],
                "seed": seed,
                "allocation_id": g_alloc,
                "governed_null_discoveries": governed.get("n_sig"),
                "ungoverned_null_discoveries": ungoverned.get("n_sig"),
                "discovery_difference": (
                    ungoverned.get("n_sig", 0) - governed.get("n_sig", 0)
                ),
                "governed_state": governed.get("inference_state") or "UNKNOWN",
                "ungoverned_state": ungoverned.get("inference_state") or "UNKNOWN",
                "governed_result_exposed_rescored": g_exposed,
                "ungoverned_result_exposed_rescored": u_exposed,
                "governed_result_withheld": g_withheld,
                "ungoverned_result_withheld": u_withheld,
                "governed_reply_overclaim_rescored": g_overclaim,
                "ungoverned_reply_overclaim_rescored": u_overclaim,
                "governed_claim_violations": ";".join(g_violations),
                "ungoverned_claim_violations": ";".join(u_violations),
            }
            tissue_pairs.append(pair)
            pairs.append(pair)

        n = len(tissue_pairs)
        tissue_rows.append(
            {
                "tissue": tissue,
                "cell_type": loaded[governed_arm]["cell_type"],
                "paired_allocations": n,
                "governed_mean_null_discoveries": round(
                    sum(r["governed_null_discoveries"] for r in tissue_pairs) / n, 2
                ),
                "ungoverned_mean_null_discoveries": round(
                    sum(r["ungoverned_null_discoveries"] for r in tissue_pairs) / n, 2
                ),
                "governed_reply_overclaim_rate": round(
                    sum(r["governed_reply_overclaim_rescored"] for r in tissue_pairs) / n, 4
                ),
                "ungoverned_reply_overclaim_rate": round(
                    sum(r["ungoverned_reply_overclaim_rescored"] for r in tissue_pairs) / n, 4
                ),
                "governed_result_withheld_rate": round(
                    sum(r["governed_result_withheld"] for r in tissue_pairs) / n, 4
                ),
                "ungoverned_result_withheld_rate": round(
                    sum(r["ungoverned_result_withheld"] for r in tissue_pairs) / n, 4
                ),
            }
        )

    n = len(pairs)
    g_over = sum(r["governed_reply_overclaim_rescored"] for r in pairs)
    u_over = sum(r["ungoverned_reply_overclaim_rescored"] for r in pairs)
    g_withheld = sum(r["governed_result_withheld"] for r in pairs)
    u_withheld = sum(r["ungoverned_result_withheld"] for r in pairs)
    summary = {
        "experiment": "same_method_governance_ablation_tms_null_pilot",
        "status": "paper_candidate_after_frozen_run",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "design": {
            "mode": MODE,
            "allocation_unit": "biological_donor",
            "paired_arms": list(ARMS),
            "method_both_arms": "pseudobulk_deseq2",
            "required_parity": [
                "allocation_id", "n_sig", "significant_genes", "design_factors",
                "covariates_used", "covariates_dropped"
            ],
            "seed_start": SEED_START,
            "requested_per_tissue": N_REQUESTED,
            "max_seed_attempts_per_tissue": MAX_ATTEMPTS,
        },
        "n_paired_allocations": n,
        "derivation": {
            "aggregator": str(Path(__file__).relative_to(ROOT)).replace("\\", "/"),
            "aggregator_sha256": _sha256(Path(__file__)),
            "claim_linter": "eval/claim_linter.py",
            "claim_linter_sha256": _sha256(ROOT / "eval/claim_linter.py"),
            "raw_inputs_are_immutable": True,
        },
        "tissue_results": tissue_rows,
        "pooled": {
            "governed_mean_null_discoveries": round(
                sum(r["governed_null_discoveries"] for r in pairs) / n, 2
            ),
            "ungoverned_mean_null_discoveries": round(
                sum(r["ungoverned_null_discoveries"] for r in pairs) / n, 2
            ),
            "governed_reply_overclaims": g_over,
            "governed_reply_overclaim_rate": round(g_over / n, 4),
            "governed_allocation_level_wilson_interval_descriptive_only": _wilson(g_over, n),
            "ungoverned_reply_overclaims": u_over,
            "ungoverned_reply_overclaim_rate": round(u_over / n, 4),
            "ungoverned_allocation_level_wilson_interval_descriptive_only": _wilson(u_over, n),
            "paired_reply_overclaim_difference": round((u_over - g_over) / n, 4),
            "governed_results_withheld": g_withheld,
            "governed_result_withheld_rate": round(g_withheld / n, 4),
            "ungoverned_results_withheld": u_withheld,
            "ungoverned_result_withheld_rate": round(u_withheld / n, 4),
            "governed_state_counts": dict(Counter(r["governed_state"] for r in pairs)),
            "ungoverned_state_counts": dict(Counter(r["ungoverned_state"] for r in pairs)),
        },
        "interpretation_boundary": (
            "Pilot isolates the governance stack while both arms use donor-level "
            "pseudobulk DESeq2 under donor-split TMS nulls. Allocations reuse "
            "donors and are not independent biological experiments. Raw null discoveries "
            "are not gene-level ground-truth false positives, and TMS is not a "
            "many-donor droplet/UMI generalization dataset."
        ),
    }

    def write_csv(path: Path, rows: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(output / "paired_allocations.csv", pairs)
    write_csv(output / "tissue_summary.csv", tissue_rows)
    write_csv(output / "raw_results_manifest.csv", manifest)
    (output / "paper_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Same-method Governance Ablation: TMS Multi-tissue Null Pilot",
        "",
        "**Status: paper-usable pilot; external many-donor validation required.**",
        "",
        "| Tissue | Pairs | Governed mean discoveries | Ungoverned mean discoveries | Governed overclaim | Ungoverned overclaim |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in tissue_rows:
        lines.append(
            f"| {row['tissue']} | {row['paired_allocations']} | "
            f"{row['governed_mean_null_discoveries']:.2f} | "
            f"{row['ungoverned_mean_null_discoveries']:.2f} | "
            f"{row['governed_reply_overclaim_rate']:.0%} | "
            f"{row['ungoverned_reply_overclaim_rate']:.0%} |"
        )
    pooled = summary["pooled"]
    lines += [
        "",
        f"Across {n} matched allocations, governed reply overclaim was "
        f"{g_over}/{n} ({g_over/n:.1%}), versus "
        f"{u_over}/{n} ({u_over/n:.1%}) ungoverned.",
        "",
        f"Governance withheld gene-level results in {g_withheld}/{n} allocations; "
        f"the ungoverned arm withheld them in {u_withheld}/{n}.",
        "",
        "Allocations reuse donors and therefore are not independent biological "
        "experiments; no biological-population confidence interval or paired p-value "
        "is claimed. Raw discovery counts are descriptive diagnostics, not proven "
        "gene-level false positives.",
        "",
        "Both arms use identical donor-level pseudobulk DESeq2 results. The aggregator "
        "refuses output if allocation, discovery count, significant genes, design, or "
        "covariates differ. External many-donor UMI validation is still required.",
    ]
    (output / "PAPER_RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    checksum_names = [
        "PAPER_RESULTS.md", "MANUSCRIPT_RESULTS.md", "paired_allocations.csv",
        "tissue_summary.csv", "raw_results_manifest.csv", "paper_summary.json",
        "protocol.json", "REPRODUCIBILITY.json", "figure_overclaim_by_tissue.png",
        "figure_overclaim_by_tissue.pdf",
    ]
    checksum_paths = [output / name for name in checksum_names if (output / name).exists()]
    checksum_paths.extend(sorted((output / "raw").glob("*.json")))
    checksum_lines = [
        f"{_sha256(path)}  {path.relative_to(output).as_posix()}" for path in checksum_paths
    ]
    (output / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=ROOT / "eval/results/ablation")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "eval/results/final_candidate/null_sweep_same_method"
    )
    parser.add_argument("--no-copy-raw", action="store_true")
    args = parser.parse_args()
    result = build(args.source, args.output, copy_raw=not args.no_copy_raw)
    print(json.dumps(result["pooled"], indent=2))


if __name__ == "__main__":
    main()
