"""Validate and package the completed 10-allocation OneK1K null pilot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
from itertools import combinations
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DATASET_MD5 = "a16487819c21506b400cd1d36f09c3e1"


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def wilson_zero(total: int) -> list[float]:
    z = 1.959963984540054
    denominator = 1 + z * z / total
    center = z * z / (2 * total) / denominator
    half = z * math.sqrt(z * z / (4 * total * total)) / denominator
    return [round(max(0, center - half), 4), round(center + half, 4)]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("D:/OneK1K/results/pilot"))
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "eval/results/final_candidate/onek1k_external_validation/pilot_null_monoc_seed3000_n10",
    )
    args = parser.parse_args()
    raw = args.output / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    manifests: list[dict] = []
    allocation_ids: set[str] = set()
    retained_sets: list[set[str]] = []
    for seed in range(3000, 3010):
        source_dir = args.source / f"seed{seed}"
        summary_path = source_dir / "summary.json"
        allocation_path = source_dir / "donor_allocation.csv"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        allocation = summary.get("allocation") or {}
        deseq = summary.get("deseq2") or {}
        if summary.get("status") != "direct_statistical_smoke_no_llm_calls":
            raise ValueError(f"Seed {seed}: invalid status")
        if allocation.get("seed") != seed:
            raise ValueError(f"Seed {seed}: seed mismatch")
        allocation_id = allocation.get("allocation_id")
        if not allocation_id or allocation_id in allocation_ids:
            raise ValueError(f"Seed {seed}: missing or duplicate allocation ID")
        allocation_ids.add(allocation_id)
        if allocation.get("n_per_group") != 227 or allocation.get("n_pairs") != 227:
            raise ValueError(f"Seed {seed}: unexpected allocation size")
        validation = deseq.get("design_validation") or {}
        if not validation.get("full_rank") or validation.get("rank") != validation.get("n_columns"):
            raise ValueError(f"Seed {seed}: design matrix is not full rank")
        with allocation_path.open(newline="", encoding="utf-8") as handle:
            donors = list(csv.DictReader(handle))
        counts = {group: sum(row["null_group"] == group for row in donors) for group in ("fake_A", "fake_B")}
        if len(donors) != 454 or counts != {"fake_A": 227, "fake_B": 227}:
            raise ValueError(f"Seed {seed}: donor CSV is unbalanced")
        retained_sets.append({row["individual"] for row in donors})

        health = summary.get("numerical_health") or {}
        rows.append({
            "seed": seed,
            "allocation_id": allocation_id,
            "donors_per_group": 227,
            "n_genes_tested": int(summary["n_genes_tested"]),
            "n_discoveries_fdr_0_05": int(summary["n_null_discoveries_fdr_0_05"]),
            "design_full_rank": True,
            "mean_within_pair_age_difference": allocation["mean_within_pair_age_difference"],
            "max_within_pair_age_difference": allocation["max_within_pair_age_difference"],
            "full_table_finite": health.get("all_test_statistics_finite"),
            "finite_diagnostic_available": bool(health),
            "worker_warning_capture": "not_available",
        })
        seed_raw = raw / f"seed{seed}"
        seed_raw.mkdir(parents=True, exist_ok=True)
        for source in (summary_path, allocation_path):
            target = seed_raw / source.name
            shutil.copy2(source, target)
            manifests.append({
                "file": target.relative_to(args.output).as_posix(),
                "size_bytes": target.stat().st_size,
                "sha256": digest(target),
            })

    same_donors = all(donors == retained_sets[0] for donors in retained_sets[1:])
    pairwise_overlaps = [len(left & right) for left, right in combinations(retained_sets, 2)]
    retained_union = set.union(*retained_sets)
    retained_intersection = set.intersection(*retained_sets)
    summary = {
        "experiment": "onek1k_many_donor_umi_constructed_null_pilot",
        "status": "external_statistical_calibration_candidate",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "filename": "OneK1K_updated_14_celltypes_980_donors.h5ad",
            "registered_md5": DATASET_MD5,
            "shape": [1266401, 32738],
            "count_source": "X_raw_integer_umi",
            "donor_column": "individual",
            "cell_type_column": "cell_label",
            "selected_cell_type": "Mono C",
        },
        "design": {
            "seeds": [3000, 3009],
            "n_allocations": 10,
            "unique_allocation_ids": len(allocation_ids),
            "eligible_donors": 524,
            "retained_donors_per_allocation": 454,
            "donors_per_group": 227,
            "same_retained_donor_set_every_allocation": same_donors,
            "unique_retained_donor_sets": len({tuple(sorted(group)) for group in retained_sets}),
            "retained_donor_union": len(retained_union),
            "retained_donor_intersection": len(retained_intersection),
            "pairwise_retained_donor_overlap_range": [min(pairwise_overlaps), max(pairwise_overlaps)],
            "pairwise_retained_donor_overlap_mean": round(sum(pairwise_overlaps) / len(pairwise_overlaps), 2),
            "assignment": "adjacent-age pairs within pool/sex; random orientation",
            "deseq2_design": "pool + sex + age + null_group",
            "statistical_unit": "donor_pseudobulk",
        },
        "primary_result": {
            "allocations_with_any_fdr_discovery": sum(row["n_discoveries_fdr_0_05"] > 0 for row in rows),
            "total_allocations": len(rows),
            "allocation_discovery_rate": 0.0,
            "allocation_level_wilson_interval_descriptive_only": wilson_zero(len(rows)),
            "total_discoveries": sum(row["n_discoveries_fdr_0_05"] for row in rows),
            "genes_tested_range": [min(row["n_genes_tested"] for row in rows), max(row["n_genes_tested"] for row in rows)],
        },
        "numerical_health": {
            "seeds_with_full_table_finite_diagnostic": 9,
            "those_seeds_all_finite": all(row["full_table_finite"] for row in rows if row["finite_diagnostic_available"]),
            "seed_3000_limitation": "Run predates finite-result diagnostics.",
            "warning_disclosure": (
                "pyDESeq2 worker processes emitted overflow/invalid-value RuntimeWarnings "
                "during optimization. Worker warnings were not captured by warnings.catch_warnings; "
                "therefore saved runtime_warning_count values are not used. Fits completed Wald "
                "testing, and seeds 3001-3009 had finite final values in all six result columns."
            ),
        },
        "interpretation_boundary": (
            "The ten allocations draw 454 donors from one 524-donor eligible cohort; 449 donors "
            "occur in every allocation and pairwise overlap is 451-454, so they are not independent "
            "cohorts. This validates donor-level pseudobulk "
            "calibration for classical monocytes in this cohort, not an external governance effect "
            "and not a zero population false-positive rate."
        ),
        "provenance": {
            "packaging_commit": git("rev-parse", "HEAD"),
            "working_tree_dirty_at_packaging": bool(git("status", "--porcelain")),
            "builder": "eval/external_validation/onek1k/package_pilot.py",
            "builder_sha256": digest(Path(__file__)),
        },
        "per_seed": rows,
    }

    def write_csv(path: Path, data: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)

    write_csv(args.output / "per_seed_summary.csv", rows)
    write_csv(args.output / "raw_manifest.csv", manifests)
    shutil.copy2(args.source / "pilot_status.json", args.output / "pilot_status.json")
    shutil.copy2(HERE / "schema_audit.json", args.output / "schema_audit.json")
    shutil.copy2(HERE / "PROTOCOL.md", args.output / "PROTOCOL.md")
    (args.output / "paper_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    result_lines = [
        "# OneK1K Many-donor UMI Null Pilot", "",
        "**Status: external statistical-calibration candidate; not an agent-governance endpoint.**", "",
        "Ten unique fake-label allocations each used 454 classical-monocyte donors "
        "(227 per group) and donor-level pseudobulk DESeq2 with `pool + sex + age + null_group`.", "",
        "All 10/10 allocations produced zero discoveries at FDR < 0.05. Between 16,067 "
        "and 16,075 genes were tested per allocation.", "",
        "The allocations heavily reuse donors: 449 occur in every allocation and pairwise overlap "
        "is 451-454 of 454. They are not independent cohorts. "
        "The result supports calibration in this well-powered setting; it does not establish a zero "
        "false-positive rate or externally validate the governance effect.", "",
        "pyDESeq2 emitted optimizer RuntimeWarnings in worker processes. Every fit completed Wald "
        "testing; all six final result columns were finite for seeds 3001-3009. Seed 3000 predates "
        "that diagnostic. Worker-warning counts saved as zero are not interpreted.", "",
    ]
    (args.output / "PAPER_RESULTS.md").write_text("\n".join(result_lines), encoding="utf-8")
    checksum_files = sorted(path for path in args.output.rglob("*") if path.is_file() and path.name != "SHA256SUMS.txt")
    (args.output / "SHA256SUMS.txt").write_text(
        "\n".join(f"{digest(path)}  {path.relative_to(args.output).as_posix()}" for path in checksum_files) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["primary_result"], indent=2))


if __name__ == "__main__":
    main()
