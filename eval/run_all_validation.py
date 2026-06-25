"""
Regenerate all validation results in one command.

Usage:
    python eval/run_all_validation.py

Environment variables (optional — override defaults):
    GSE_DATA_DIR   Directory for GSE226225 extraction and .h5ad cache (default: data/gse226225/)
    GSE_TAR_PATH   Path to downloaded GSE226225_RAW.tar (default: $GSE_DATA_DIR/GSE226225_RAW.tar)

Outputs:
    eval/results/validation/    GSE226225 metrics, report, UMAP, marker comparison
    eval/results/cross_tissue/  TMS cross-tissue metrics and report
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

SCRIPTS = [
    ("GSE226225 validation", ROOT / "eval" / "compute_gse226225_validation.py"),
    ("Cross-tissue TMS validation", ROOT / "eval" / "run_cross_tissue_validation.py"),
]


def run(label: str, script: Path):
    print(f"\n{'=' * 60}")
    print(f"Running: {label}")
    print(f"Script:  {script.relative_to(ROOT)}")
    print("=" * 60)

    result = subprocess.run(
        [PYTHON, str(script)],
        cwd=str(ROOT),
    )

    if result.returncode != 0:
        print(f"\nFAILED: {label} (exit code {result.returncode})")
        return False

    print(f"\nOK: {label}")
    return True


def main():
    print("SENESCENCE AGENT — FULL VALIDATION SUITE")
    print("=" * 60)
    print(f"Root: {ROOT}")
    print(f"Python: {PYTHON}")

    results = {}
    for label, script in SCRIPTS:
        if not script.exists():
            print(f"\nSKIPPED: {label} — script not found: {script}")
            results[label] = "missing"
            continue
        ok = run(label, script)
        results[label] = "ok" if ok else "failed"

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for label, status in results.items():
        icon = "OK" if status == "ok" else ("SKIP" if status == "missing" else "FAIL")
        print(f"  [{icon}] {label}")

    failed = [l for l, s in results.items() if s == "failed"]
    if failed:
        print(f"\n{len(failed)} script(s) failed. Check output above.")
        sys.exit(1)
    else:
        print("\nAll validation complete.")
        print(f"  Results: {ROOT / 'eval' / 'results'}")


if __name__ == "__main__":
    main()
