"""Resumable OneK1K null pilot orchestrator.

Each seed is a separate subprocess and checkpoint. Statistical and paired LLM
stages are deliberately separate so an expensive DE batch never silently
starts API calls.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def valid_statistical(path: Path, seed: int) -> bool:
    record = load_json(path)
    return bool(
        record
        and record.get("status") == "direct_statistical_smoke_no_llm_calls"
        and int((record.get("allocation") or {}).get("seed", -1)) == seed
        and record.get("n_genes_tested", 0) > 0
        and record.get("n_null_discoveries_fdr_0_05") is not None
    )


def valid_paired(path: Path) -> bool:
    record = load_json(path)
    return bool(
        record
        and record.get("status") == "paired_frozen_result_communication_smoke"
        and (record.get("arm_parity") or {}).get("passed") is True
        and isinstance((record.get("governed") or {}).get("violations"), list)
        and isinstance((record.get("ungoverned") or {}).get("violations"), list)
    )


def write_status(path: Path, args: argparse.Namespace, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.data),
        "cell_label": args.cell_label,
        "seed_start": args.seed_start,
        "n_seeds": args.n_seeds,
        "stage": args.stage,
        "seeds": rows,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_checked(command: list[str]) -> None:
    print("\n> " + subprocess.list2cmdline(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode:
        raise RuntimeError(f"Child process exited with code {completed.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("D:/OneK1K/results/pilot"))
    parser.add_argument("--cell-label", default="Mono C")
    parser.add_argument("--seed-start", type=int, default=3000)
    parser.add_argument("--n-seeds", type=int, default=10)
    parser.add_argument("--stage", choices=("statistical", "paired", "all"), default="statistical")
    parser.add_argument(
        "--reuse-first-statistical", type=Path,
        help="Existing seed-start directory containing summary.json and donor_allocation.csv.",
    )
    parser.add_argument(
        "--reuse-first-paired", type=Path,
        help="Existing valid paired JSON for seed-start; copied without an API call.",
    )
    parser.add_argument(
        "--max-new-api", type=int, default=0,
        help="Hard cap on new paired LLM calls. Required for paired/all stages.",
    )
    args = parser.parse_args()
    args.output_root = args.output_root.resolve()
    status_path = args.output_root / "pilot_status.json"
    rows: list[dict] = []
    new_api_calls = 0

    try:
        for seed in range(args.seed_start, args.seed_start + args.n_seeds):
            seed_dir = args.output_root / f"seed{seed}"
            summary = seed_dir / "summary.json"
            paired = seed_dir / "paired_frozen_smoke.json"
            row = {"seed": seed, "statistical": "pending", "paired": "pending"}
            rows.append(row)

            if seed == args.seed_start and not summary.exists() and args.reuse_first_statistical:
                source_summary = args.reuse_first_statistical / "summary.json"
                if not valid_statistical(source_summary, seed):
                    raise RuntimeError("--reuse-first-statistical is not a valid seed checkpoint")
                seed_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_summary, summary)
                source_allocation = args.reuse_first_statistical / "donor_allocation.csv"
                if source_allocation.exists():
                    shutil.copy2(source_allocation, seed_dir / "donor_allocation.csv")

            if seed == args.seed_start and not paired.exists() and args.reuse_first_paired:
                if not valid_paired(args.reuse_first_paired):
                    raise RuntimeError("--reuse-first-paired is not a valid paired checkpoint")
                seed_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(args.reuse_first_paired, paired)

            if valid_statistical(summary, seed):
                row["statistical"] = "reused"
            elif args.stage in {"statistical", "all"}:
                run_checked([
                    sys.executable, str(HERE / "direct_null_smoke.py"), str(args.data),
                    "--cell-label", args.cell_label, "--seed", str(seed),
                    "--output-dir", str(seed_dir), "--summary-only",
                ])
                if not valid_statistical(summary, seed):
                    raise RuntimeError(f"Seed {seed} did not produce a valid summary")
                row["statistical"] = "completed"
            else:
                row["statistical"] = "missing"

            if valid_paired(paired):
                row["paired"] = "reused"
            elif args.stage in {"paired", "all"}:
                if row["statistical"] == "missing":
                    raise RuntimeError(f"Seed {seed} has no statistical checkpoint")
                if new_api_calls >= args.max_new_api:
                    raise RuntimeError(
                        f"API budget reached ({args.max_new_api}); resume with a new explicit budget"
                    )
                run_checked([
                    sys.executable, str(HERE / "paired_frozen_smoke.py"), str(summary),
                    "--output", str(paired),
                ])
                new_api_calls += 1
                if not valid_paired(paired):
                    raise RuntimeError(f"Seed {seed} did not produce a valid paired checkpoint")
                row["paired"] = "completed"

            write_status(status_path, args, rows)
    except Exception as exc:
        if rows:
            rows[-1]["error"] = str(exc)
        write_status(status_path, args, rows)
        raise SystemExit(f"STOPPED: {exc}") from exc

    print(json.dumps({
        "status": "complete",
        "checkpoint": str(status_path),
        "new_api_calls": new_api_calls,
        "seeds": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
