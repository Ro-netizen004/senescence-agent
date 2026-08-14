"""Refresh and render diagnostic summaries from an existing agent-null JSON."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "backend"))

from agent_null_sweep import aggregate_diagnostics  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Analyze saved null-sweep diagnostics")
    parser.add_argument("json_path", type=Path)
    args = parser.parse_args()
    path = args.json_path.resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    diagnostics = aggregate_diagnostics(data.get("permutations") or [])
    data["diagnostics"] = diagnostics
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    sensitivity = diagnostics["donor_sensitivity"]
    lines = [
        "# Null Diagnostic Sensitivity Report",
        "",
        f"- Dataset: {data.get('dataset')}",
        f"- Cell type: {data.get('cell_type')}",
        f"- Valid allocations analyzed: {diagnostics['n_runs_with_diagnostics']}",
        "",
        "## Discovery Stability",
        "",
        f"- Null discoveries: {diagnostics['null_discovery_distribution']}",
        f"- Pairwise gene Jaccard: {diagnostics['gene_overlap']['pairwise_jaccard']}",
        f"- Nearest-partition discovery difference: {sensitivity['nearest_partition_discovery_difference']}",
        f"- Nearest-partition gene Jaccard: {sensitivity['nearest_partition_gene_jaccard']}",
        "",
        "## Donor Exclusion",
        "",
        "| Donor | Excluded n | Excluded mean | Retained n | Retained mean | Difference |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in sensitivity["donor_exclusion_effects"]:
        excluded, retained = row["excluded"], row["retained"]
        lines.append(
            f"| {row['donor']} | {excluded['n']} | {excluded['mean']} | "
            f"{retained['n']} | {retained['mean']} | "
            f"{row['mean_discovery_difference_excluded_minus_retained']} |"
        )
    lines += [
        "",
        "## Interpretation Boundary",
        "",
        sensitivity["method"],
        "",
        "PCA distance and partition sensitivity identify influential donor profiles; "
        "they do not establish a causal technical defect in a donor.",
    ]
    report_path = path.with_suffix(".diagnostics.md")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Updated: {path}")
    print(f"Saved:   {report_path}")


if __name__ == "__main__":
    main()
