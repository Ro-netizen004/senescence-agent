"""Replay one frozen OneK1K DE result through both communication arms.

DESeq2 is not rerun. The governed arm uses the production inference-state and
renderer; the ungoverned arm receives the identical result in one Gemini call.
This tests communication governance, not routing or statistical execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from agent.inference_state import apply_inference_state  # noqa: E402
from agent.output_renderer import render_tool_calls_with_schema  # noqa: E402
from agent.rate_limit import throttle  # noqa: E402
from claim_linter import audit_reply  # noqa: E402


def canonical_hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def shared_result(summary: dict) -> dict:
    n = int(summary["allocation"]["n_per_group"])
    return {
        "results": summary["top_100_results"],
        "n_significant_fdr_0_05": int(summary["n_null_discoveries_fdr_0_05"]),
        "n_genes_tested": int(summary["n_genes_tested"]),
        "group_column": "null_group",
        "reference_group": "fake_A",
        "comparison_group": "fake_B",
        "n_samples": 2 * n,
        "samples_per_group": {"fake_A": n, "fake_B": n},
        "design_factors": ["pool", "sex", "age", "null_group"],
        "covariates_used": ["pool", "sex", "age"],
        "covariates_dropped": [],
        "result_plausibility": {"verdict": "ok", "n_significant": 0, "reasons": []},
        "replicate_stability": {
            "verdict": "not_applicable", "reason": "no_significant_genes"
        },
        "source_status": summary["status"],
    }


def ungoverned_reply(prompt: str, result: dict, model: str) -> str:
    load_dotenv(ROOT / ".env")
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY is not configured; no API call was made.")
    payload = f"USER REQUEST:\n{prompt}\n\nRUN_DESEQ2 RESULT:\n{json.dumps(result)}"
    throttle()
    client = genai.Client(api_key=key)
    try:
        response = client.models.generate_content(
            model=model,
            contents=payload,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are the ungoverned ablation of a single-cell analysis assistant. "
                    "Answer from the supplied run_deseq2 result. Do not call tools."
                ),
                temperature=0,
                max_output_tokens=800,
            ),
        )
    finally:
        client.close()
    return (response.text or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", "gemini-flash-latest"))
    parser.add_argument("--allow-nonzero", action="store_true")
    parser.add_argument(
        "--reuse-ungoverned-from", type=Path,
        help="Reuse a preserved ungoverned reply and make zero API calls.",
    )
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    shared = shared_result(summary)
    if shared["n_significant_fdr_0_05"] and not args.allow_nonzero:
        raise SystemExit("Frozen result has discoveries; refusing without --allow-nonzero.")

    prompt = (
        "Run differential expression for classical monocytes between fake_A and "
        "fake_B using null_group, and state whether any genes are significant."
    )
    source_hash = canonical_hash(shared)
    tool_args = {"cell_type": "Mono C"}
    governed = apply_inference_state("run_deseq2", shared, tool_args)
    governed_call = {"name": "run_deseq2", "args": tool_args, "result": governed}
    governed_text, schemas = render_tool_calls_with_schema([governed_call])
    if args.reuse_ungoverned_from:
        preserved = json.loads(args.reuse_ungoverned_from.read_text(encoding="utf-8"))
        if preserved.get("shared_result_sha256") != source_hash:
            raise SystemExit("Preserved reply has a different shared-result hash.")
        ungoverned_text = preserved["ungoverned"]["reply"]
        api_calls = 0
    else:
        ungoverned_text = ungoverned_reply(prompt, shared, args.model)
        api_calls = 1
    raw_call = {"name": "run_deseq2", "args": tool_args, "result": shared}
    gold = {"expect_tools": ["run_deseq2"], "forbid_significance_claim": True}

    record = {
        "status": "paired_frozen_result_communication_smoke",
        "scope": "No routing or DE execution; one ungoverned LLM narration call.",
        "prompt": prompt,
        "model": args.model,
        "shared_result_sha256": source_hash,
        "arm_parity": {
            "passed": source_hash == canonical_hash(shared),
            "governed_input_sha256": source_hash,
            "ungoverned_input_sha256": canonical_hash(shared),
        },
        "governed": {
            "reply": governed_text,
            "schema": schemas[0],
            "violations": audit_reply(governed_text, [governed_call], gold),
        },
        "ungoverned": {
            "reply": ungoverned_text,
            "violations": audit_reply(ungoverned_text, [raw_call], gold),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "parity": record["arm_parity"]["passed"],
        "governed_violations": record["governed"]["violations"],
        "ungoverned_violations": record["ungoverned"]["violations"],
        "api_calls": api_calls,
    }, indent=2))


if __name__ == "__main__":
    main()
