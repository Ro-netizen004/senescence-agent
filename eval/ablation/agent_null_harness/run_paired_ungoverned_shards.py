"""Run only missing ungoverned allocations from the frozen governed worklist."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "eval/results/ablation"
DATA = ROOT / "backend/data"

CONFIGS = [
    ("Kidney", "epithelial cell of proximal tubule"),
    ("Liver", "hepatocyte"),
    ("Spleen", "B cell"),
    ("Aorta", "aortic endothelial cell"),
    ("Limb_Muscle", "skeletal muscle satellite cell"),
]


def _slug(value: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")


def _governed_path(tissue: str, cell_type: str) -> Path:
    return OUT / (
        f"agent_null_{tissue}_{_slug(cell_type)}_governed_same_method_"
        "stratified_valid_ordinary_seed2000_n30.json"
    )


def _shard_path(tissue: str, cell_type: str, seed: int) -> Path:
    # agent_null_sweep removes punctuation from the dataset-derived tissue name.
    output_tissue = "".join(ch for ch in tissue if ch.isalnum())
    return OUT / (
        f"agent_null_{output_tissue}_{_slug(cell_type)}_ungoverned_same_method_"
        f"stratified_valid_ordinary_seed{seed}_n1.json"
    )


def _parity_error(governed: dict, ungoverned: dict) -> str | None:
    fields = ("n_sig", "design_factors", "covariates_used", "covariates_dropped")
    if (governed.get("meta") or {}).get("allocation_id") != (ungoverned.get("meta") or {}).get("allocation_id"):
        return "allocation_id"
    for field in fields:
        if governed.get(field) != ungoverned.get(field):
            return field
    g_genes = set((governed.get("evaluation_diagnostics") or {}).get("significant_genes") or [])
    u_genes = set((ungoverned.get("evaluation_diagnostics") or {}).get("significant_genes") or [])
    return None if g_genes == u_genes else "significant_genes"


def _load_valid_shard(path: Path, governed: dict) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("permutations") or []
        return (
            payload.get("n_perm_agent_errors", 0) == 0
            and len(rows) == 1
            and _parity_error(governed, rows[0]) is None
        )
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=15.0)
    args = parser.parse_args()
    if args.max_new < 1:
        raise SystemExit("--max-new must be positive")

    work = []
    for tissue, cell_type in CONFIGS:
        governed_path = _governed_path(tissue, cell_type)
        governed_payload = json.loads(governed_path.read_text(encoding="utf-8"))
        for row in governed_payload["permutations"]:
            if not row.get("skipped") and not row.get("agent_error"):
                work.append((tissue, cell_type, row))

    completed = 0
    skipped = 0
    for tissue, cell_type, governed in work:
        seed = int(governed["seed"])
        shard = _shard_path(tissue, cell_type, seed)
        if _load_valid_shard(shard, governed):
            skipped += 1
            continue
        if completed >= args.max_new:
            break

        data_path = DATA / f"tabula-muris-senis-facs-processed-official-annotations-{tissue}.h5ad"
        command = [
            sys.executable, str(HERE / "agent_null_sweep.py"),
            "--data", str(data_path), "--cell-type", cell_type,
            "--n-perm", "1", "--seed", str(seed),
            "--arm", "ungoverned_same_method", "--mode", "stratified",
            "--design", "valid", "--prompt-style", "ordinary",
        ]
        print(f"RUN {tissue} / {cell_type} / seed {seed}", flush=True)
        result = subprocess.run(command, cwd=str(ROOT), check=False)
        if result.returncode != 0:
            raise SystemExit(f"Stopped after failed shard {tissue} seed {seed}")
        if not _load_valid_shard(shard, governed):
            raise SystemExit(f"Parity validation failed for {tissue} seed {seed}")
        completed += 1
        print(f"PASS {tissue} seed {seed}; new={completed}, reused={skipped}", flush=True)
        if completed < args.max_new:
            time.sleep(max(0.0, args.delay_seconds))

    remaining = sum(
        not _load_valid_shard(_shard_path(t, c, int(row["seed"])), row)
        for t, c, row in work
    )
    print(f"DONE new={completed} reused={skipped} remaining={remaining}")


if __name__ == "__main__":
    main()
