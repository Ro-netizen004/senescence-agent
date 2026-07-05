"""
Run all ablation studies.

Usage:
    python eval/ablation/run_all_ablations.py

Outputs:
    eval/results/ablation/pseudorep_results.json + pseudorep_report.md
    eval/results/ablation/ism_results.json       + ism_report.md
    eval/results/ablation/router_results.json    + router_report.md
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

ABLATIONS = [
    ("Pseudoreplication guard", "ablation_pseudorep"),
    ("Inference state machine", "ablation_ism"),
    ("Keyword router",          "ablation_router"),
]


def main():
    print("SENESCENCE AGENT — ABLATION SUITE")
    print("=" * 50)

    results = {}
    for label, module_name in ABLATIONS:
        print(f"\n{'='*50}")
        print(f"Running: {label}")
        print("=" * 50)
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                module_name,
                Path(__file__).parent / f"{module_name}.py"
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.run()
            results[label] = "ok"
        except Exception as e:
            print(f"\nFAILED: {label} — {e}")
            results[label] = "failed"

    print(f"\n{'='*50}")
    print("ABLATION SUMMARY")
    print("=" * 50)
    for label, status in results.items():
        icon = "OK" if status == "ok" else "FAIL"
        print(f"  [{icon}] {label}")

    out_dir = ROOT / "eval" / "results" / "ablation"
    print(f"\nResults in: {out_dir}")


if __name__ == "__main__":
    main()
