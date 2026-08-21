"""Large, zero-LLM/zero-DESeq2 sweep of the production confounding gate."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent.admissibility import check_admissibility  # noqa: E402
from agent.pipeline import ensure_pipeline  # noqa: E402
from agent_null_sweep import score_confounding_design  # noqa: E402
from null_builder import (  # noqa: E402
    FAKE_OLD, FAKE_YOUNG, NULL_GROUP_COLUMN, build_null_adata, prepare_null_source,
)

DESIGNS = (
    "confounded",
    "confounded_partial",
    "covariate_balanced",
    "contrast_alias",
    "contrast_alias_with_batch",
)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_design(
    source, data: Path, cell_type: str, design: str, seed: int, n_perm: int,
    checkpoint: Path,
) -> dict:
    rows = []
    attempts = 0
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        expected = {
            "dataset": data.name, "cell_type": cell_type, "design": design,
            "seed_start": seed, "n_requested": n_perm,
        }
        observed = {key: saved.get(key) for key in expected}
        if observed != expected:
            raise RuntimeError(
                f"Checkpoint configuration mismatch for {design}: {observed} != {expected}"
            )
        rows = list(saved.get("rows") or [])
        attempts = int(saved.get("attempts") or 0)
        print(f"  resuming {len(rows)}/{n_perm} after {attempts} attempts", flush=True)
    seen = {row["allocation_id"] for row in rows}
    max_attempts = max(20, n_perm * 20)
    while len(rows) < n_perm and attempts < max_attempts:
        current_seed = seed + attempts
        attempts += 1
        sub, meta = build_null_adata(
            data, cell_type, current_seed, mode="stratified", design=design,
            source_adata=source,
        )
        allocation_id = meta["allocation_id"]
        if allocation_id in seen:
            del sub
            gc.collect()
            atomic_json(checkpoint, {
                "dataset": data.name, "cell_type": cell_type, "design": design,
                "seed_start": seed, "n_requested": n_perm,
                "attempts": attempts, "rows": rows,
            })
            continue
        seen.add(allocation_id)
        ensure_pipeline(sub, "mouse")
        if design in {"contrast_alias", "contrast_alias_with_batch"}:
            profile = sub.uns.setdefault("dataset_profile", {})
            aliases = dict(profile.get("contrast_aliases") or {})
            aliases[NULL_GROUP_COLUMN] = ["null_group_alias"]
            profile["contrast_aliases"] = aliases
        result = check_admissibility("run_deseq2", {
            "cell_type": cell_type,
            "group_column": NULL_GROUP_COLUMN,
            "reference_group": FAKE_YOUNG,
            "comparison_group": FAKE_OLD,
        }, sub)
        blocked_reasons = list(result.get("blocked_reasons") or [])
        rows.append({
            "seed": current_seed,
            "allocation_id": allocation_id,
            "n_samples": meta["n_mice"],
            "blocked": not result["admissible"],
            "error": " ".join(blocked_reasons) if blocked_reasons else None,
            "blocked_reasons": blocked_reasons,
            "admissibility_warnings": list(result.get("warnings") or []),
            "checks": result.get("checks") or {},
        })
        del sub
        gc.collect()
        atomic_json(checkpoint, {
            "dataset": data.name, "cell_type": cell_type, "design": design,
            "seed_start": seed, "n_requested": n_perm,
            "attempts": attempts, "rows": rows,
        })
        print(f"  checkpoint {len(rows)}/{n_perm} seed={current_seed}", flush=True)
    if len(rows) < n_perm:
        raise RuntimeError(
            f"{design}: only {len(rows)} unique allocations after {attempts} attempts"
        )
    return {
        "design": design,
        "n_requested": n_perm,
        "n_completed": len(rows),
        "attempts": attempts,
        "evaluation": score_confounding_design(design, rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--cell-type", default="B cell")
    parser.add_argument("--n-perm", type=int, default=30)
    parser.add_argument("--seed", type=int, default=5000)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "eval/results/final_candidate/confound_gate_sweep.json",
    )
    args = parser.parse_args()
    if args.output.exists():
        completed = json.loads(args.output.read_text(encoding="utf-8"))
        if (
            completed.get("status") == "complete_gate_only_no_llm_no_deseq2"
            and completed.get("dataset") == args.data.name
            and completed.get("cell_type") == args.cell_type
            and completed.get("seed_start") == args.seed
            and completed.get("n_per_design") == args.n_perm
        ):
            print(f"Already complete: {args.output.resolve()}")
            return
        raise SystemExit("Output exists with a different or incomplete configuration.")
    checkpoint_dir = args.output.parent / f"{args.output.stem}_checkpoints"
    source = prepare_null_source(args.data, args.cell_type)
    results = []
    for design in DESIGNS:
        print(f"\n{design}: {args.n_perm} unique allocations", flush=True)
        result = run_design(
            source, args.data, args.cell_type, design, args.seed, args.n_perm,
            checkpoint_dir / f"{design}.json",
        )
        results.append(result)
        print(json.dumps(result["evaluation"], indent=2), flush=True)
    payload = {
        "status": "complete_gate_only_no_llm_no_deseq2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": args.data.name,
        "cell_type": args.cell_type,
        "mode": "stratified",
        "seed_start": args.seed,
        "n_per_design": args.n_perm,
        "designs": results,
    }
    atomic_json(args.output, payload)
    print(f"\nSaved: {args.output.resolve()}")


if __name__ == "__main__":
    main()
