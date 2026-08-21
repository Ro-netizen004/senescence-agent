"""Archive reproducibility metadata for the frozen paired null experiment."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "eval/results/final_candidate/null_sweep_same_method"
DATA = ROOT / "backend/data"
DATASETS = ["Kidney", "Liver", "Spleen", "Aorta", "Limb_Muscle"]
PACKAGES = ["anndata", "google-genai", "matplotlib", "numpy", "pandas", "pydeseq2", "scanpy", "scipy"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    protocol = json.loads((PACKAGE / "protocol.json").read_text(encoding="utf-8"))
    dataset_records = []
    for tissue in DATASETS:
        path = DATA / f"tabula-muris-senis-facs-processed-official-annotations-{tissue}.h5ad"
        dataset_records.append({
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        })

    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None

    raw_files = sorted((PACKAGE / "raw").glob("*.json"))
    raw_records = [
        {"file": f"raw/{path.name}", "size_bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in raw_files
    ]
    metadata = {
        "experiment": protocol["experiment"],
        "archived_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation_date_utc": "2026-08-18",
        "code": {
            "packaging_commit": git("rev-parse", "HEAD"),
            "packaging_commit_timestamp": git("show", "-s", "--format=%cI", "HEAD"),
            "packaging_commit_subject": git("show", "-s", "--format=%s", "HEAD"),
            "agent_statistical_revision": protocol["agent_statistical_revision"],
            "memory_safe_harness_revision": protocol["memory_safe_harness_revision"],
        },
        "runtime": {"python": sys.version.split()[0], "packages": versions},
        "llm": {
            "provider": "Google Gemini via google-genai",
            "model": "gemini-flash-latest",
            "model_resolution": "GEMINI_MODEL was unset; repository default applied",
            "agent_temperature": 0,
            "planner_temperature": 0,
            "api_key_archived": False,
        },
        "inference_settings": protocol["analysis_specification_environment"],
        "method": protocol["method_both_arms"],
        "statistical_unit": protocol["statistical_unit_both_arms"],
        "null_construction": protocol["null_construction"],
        "seed_schedule": protocol["seed_schedule"],
        "datasets": dataset_records,
        "raw_canonical_inputs": raw_records,
        "prompts": {
            "style": protocol["null_construction"]["prompt_style"],
            "template": "Which genes differ between fake_A and fake_B in {cell_type}?",
        },
        "secret_handling": "No API keys or environment secret values are archived.",
    }
    (PACKAGE / "REPRODUCIBILITY.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    checksum_files = [
        "PAPER_RESULTS.md", "MANUSCRIPT_RESULTS.md", "paired_allocations.csv",
        "tissue_summary.csv", "raw_results_manifest.csv", "paper_summary.json",
        "protocol.json", "REPRODUCIBILITY.json", "figure_overclaim_by_tissue.png",
        "figure_overclaim_by_tissue.pdf",
    ]
    lines = [f"{sha256(PACKAGE / name)}  {name}" for name in checksum_files]
    lines.extend(f"{row['sha256']}  {row['file']}" for row in raw_records)
    (PACKAGE / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Archived {len(dataset_records)} datasets and {len(raw_records)} canonical raw inputs")


if __name__ == "__main__":
    main()
