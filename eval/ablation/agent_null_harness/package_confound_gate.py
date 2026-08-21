"""Package the completed confound-gate sweep as an auditable paper artifact."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPLEEN_SHA256 = "ea3ebbb6d68e9c69238eb276eb0f3454fa404e2505bd18daea5d6dac7a69f309"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "eval/results/final_candidate/confound_gate",
    )
    args = parser.parse_args()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    if source.get("status") != "complete_gate_only_no_llm_no_deseq2":
        raise ValueError("Source sweep is not complete")
    if source.get("n_per_design") != 30 or len(source.get("designs") or []) != 5:
        raise ValueError("Expected five designs with 30 allocations each")

    expected = {
        "confounded": ("recall", 1.0),
        "confounded_partial": ("allow_rate", 1.0),
        "covariate_balanced": ("specificity", 1.0),
        "contrast_alias": ("allow_rate", 1.0),
        "contrast_alias_with_batch": ("recall", 1.0),
    }
    rows = []
    allocation_sets = []
    for result in source["designs"]:
        design = result["design"]
        evaluation = result["evaluation"]
        if result["n_completed"] != 30 or len({r["allocation_id"] for r in result["rows"]}) != 30:
            raise ValueError(f"{design}: incomplete or duplicate allocations")
        if (evaluation["metric_name"], evaluation["metric"]) != expected[design]:
            raise ValueError(f"{design}: registered endpoint failed")
        if evaluation["n_unrelated_blocks"]:
            raise ValueError(f"{design}: unrelated blocks detected")
        if design == "confounded_partial" and evaluation["partial_warning_rate"] != 1.0:
            raise ValueError("Partial-confound warning endpoint failed")
        if design == "contrast_alias" and evaluation["alias_warning_rate"] != 1.0:
            raise ValueError("Alias warning endpoint failed")
        allocation_sets.append({r["allocation_id"] for r in result["rows"]})
        rows.append({
            "design": design,
            "n_allocations": result["n_completed"],
            "attempts": result["attempts"],
            "expected_outcome": evaluation["expected_outcome"],
            "metric_name": evaluation["metric_name"],
            "metric": evaluation["metric"],
            "descriptive_interval_low": evaluation["metric_ci95"][0],
            "descriptive_interval_high": evaluation["metric_ci95"][1],
            "unrelated_blocks": evaluation["n_unrelated_blocks"],
            "partial_warning_rate": evaluation["partial_warning_rate"],
            "alias_warning_rate": evaluation["alias_warning_rate"],
        })
    if not all(group == allocation_sets[0] for group in allocation_sets[1:]):
        raise ValueError("Challenge designs do not use the same allocation set")

    args.output.mkdir(parents=True, exist_ok=True)
    raw = args.output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.source, raw / args.source.name)
    checkpoint_source = args.source.parent / f"{args.source.stem}_checkpoints"
    for path in checkpoint_source.glob("*.json"):
        shutil.copy2(path, raw / f"checkpoint_{path.name}")
    with (args.output / "design_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "experiment": "tms_confound_gate_functional_validation",
        "status": "paper_candidate_functional_validation",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "filename": source["dataset"], "sha256": SPLEEN_SHA256,
            "cell_type": source["cell_type"],
        },
        "design": {
            "n_challenge_types": 5,
            "n_allocations_per_challenge": 30,
            "total_gate_decisions": 150,
            "unique_donor_allocations": 30,
            "same_allocations_across_challenges": True,
            "llm_calls": 0,
            "deseq2_calls": 0,
        },
        "results": rows,
        "primary_conclusion": (
            "All 150 gate decisions matched their registered behavior with no unrelated blocks."
        ),
        "interpretation_boundary": (
            "This is a deterministic functional validation using synthetic metadata challenges "
            "on 30 reused TMS donor allocations, not 150 independent biological cohorts. "
            "Intervals are descriptive only and should not be interpreted as population coverage."
        ),
    }
    (args.output / "paper_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Confound-gate Functional Validation", "",
        "**Status: paper candidate functional validation.**", "",
        "The production admissibility gate was evaluated on five paired metadata challenges "
        "across 30 unique TMS Spleen B-cell donor allocations (150 decisions total).", "",
        "| Challenge | n | Endpoint | Result |", "|---|---:|---|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['design']} | 30 | {row['metric_name']} | {row['metric']:.0%} |")
    lines += [
        "", "Partial-confound warnings were issued in 30/30 cases; registered-alias warnings "
        "were issued in 30/30 cases. There were no unrelated blocks.", "",
        "No LLM or DESeq2 calls were made. The same donor allocations are reused across "
        "synthetic challenge types; this is functional validation, not independent-cohort evidence.", "",
    ]
    (args.output / "PAPER_RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    files = sorted(p for p in args.output.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
    (args.output / "SHA256SUMS.txt").write_text(
        "\n".join(f"{sha256(path)}  {path.relative_to(args.output).as_posix()}" for path in files) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["design"], indent=2))


if __name__ == "__main__":
    main()
