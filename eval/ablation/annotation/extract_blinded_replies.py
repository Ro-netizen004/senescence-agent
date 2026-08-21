"""Extract governed and ungoverned replies into a blinded CSV for human annotation.

Reads the raw same-method JSON result files and outputs a shuffled, blinded CSV
where annotators cannot see which arm produced which reply.

Usage:
  python eval/ablation/annotation/extract_blinded_replies.py \
      --raw-dir eval/results/final_candidate/null_sweep_same_method/raw \
      --output eval/ablation/annotation/blinded_replies.csv \
      --key eval/ablation/annotation/blinded_key.json

The key file maps blinded IDs back to arm/tissue/seed for scoring after annotation.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _normalize_arm(value: object) -> str | None:
    """Map registered arm names without substring ambiguity."""
    arm = str(value or "").strip().lower()
    if arm == "ungoverned" or arm.startswith("ungoverned_"):
        return "ungoverned"
    if arm == "governed" or arm.startswith("governed_"):
        return "governed"
    return None


def _source_arm(data: dict, source: Path) -> str | None:
    arm = _normalize_arm(data.get("arm"))
    if arm:
        return arm

    # Check the longer token first: "ungoverned" contains "governed".
    if "_ungoverned_" in source.stem:
        return "ungoverned"
    if "_governed_" in source.stem:
        return "governed"
    return None


def extract_replies(raw_dir: Path) -> list[dict]:
    rows = []
    for f in sorted(raw_dir.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        allocations = data.get("permutations")
        if allocations is None:
            allocations = data.get("allocations")
        if allocations is None:
            allocations = data.get("results", [])
        arm = _source_arm(data, f)
        tissue = data.get("dataset") or f.stem

        for i, alloc in enumerate(allocations):
            if "governed" in alloc and "ungoverned" in alloc:
                for a in ["governed", "ungoverned"]:
                    r = alloc[a].get("reply", "")
                    if r:
                        rows.append({
                            "tissue": tissue,
                            "arm": a,
                            "seed": alloc.get("seed", ""),
                            "allocation_index": i,
                            "reply": r,
                            "source_file": f.name,
                        })
                continue

            if arm is None:
                raise ValueError(
                    f"Cannot determine governed/ungoverned arm for {f.name}"
                )

            reply = alloc.get("reply", "")
            if not reply and arm in alloc:
                reply = alloc[arm].get("reply", "")

            if reply:
                rows.append({
                    "tissue": tissue,
                    "arm": arm,
                    "seed": alloc.get("seed", ""),
                    "allocation_index": i,
                    "reply": reply,
                    "source_file": f.name,
                })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--expected-per-arm", type=int, default=78,
        help="Fail unless this many replies are found per arm (default: 78)",
    )
    args = parser.parse_args()

    replies = extract_replies(args.raw_dir)
    if not replies:
        print("No replies found. Check the raw JSON structure.", file=sys.stderr)
        sys.exit(1)

    n_gov = sum(1 for r in replies if r["arm"] == "governed")
    n_ungov = sum(1 for r in replies if r["arm"] == "ungoverned")
    if args.expected_per_arm >= 0 and (
        n_gov != args.expected_per_arm or n_ungov != args.expected_per_arm
    ):
        print(
            f"Reply-count validation failed: governed={n_gov}, "
            f"ungoverned={n_ungov}, expected={args.expected_per_arm} per arm",
            file=sys.stderr,
        )
        sys.exit(1)

    rng = random.Random(args.seed)
    rng.shuffle(replies)

    key_data = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "blinded_id",
            "reply_text",
            "makes_positive_significance_claim",
            "makes_descriptive_claim_only",
            "explicitly_withholds_inference",
            "exposes_gene_level_results",
            "correctly_explains_limitation",
            "contains_unsupported_biological_interpretation",
            "annotator_notes",
        ])
        for i, row in enumerate(replies):
            blinded_id = f"R{i:04d}"
            reply_text = row["reply"].replace("\n", " ").strip()
            writer.writerow([blinded_id, reply_text, "", "", "", "", "", "", ""])
            key_data.append({
                "blinded_id": blinded_id,
                "arm": row["arm"],
                "tissue": row["tissue"],
                "seed": row["seed"],
                "allocation_index": row["allocation_index"],
                "source_file": row["source_file"],
            })

    args.key.parent.mkdir(parents=True, exist_ok=True)
    args.key.write_text(json.dumps(key_data, indent=2) + "\n", encoding="utf-8")

    print(f"Extracted {len(replies)} replies ({n_gov} governed, {n_ungov} ungoverned)")
    print(f"Blinded CSV: {args.output}")
    print(f"Answer key:  {args.key}")
    print(f"\nAnnotation protocol:")
    print(f"  1. Two annotators independently label each row (columns C-H)")
    print(f"  2. Use Yes/No for each column")
    print(f"  3. Do NOT look at the key file until both annotators finish")
    print(f"  4. Compute Cohen's kappa on the significance-claim column")
    print(f"  5. Resolve disagreements with a third reviewer")


if __name__ == "__main__":
    main()
