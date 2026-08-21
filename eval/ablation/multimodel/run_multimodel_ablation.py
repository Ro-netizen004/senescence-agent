"""Multi-model response-generation ablation.

Replays frozen same-method DESeq2 results through multiple LLM families
to test whether governance is model-independent. DESeq2 is NOT rerun.

The governed arm is deterministic (no LLM) and identical across all models.
The ungoverned arm sends the same frozen result to each LLM family.

Usage:
  python eval/ablation/multimodel/run_multimodel_ablation.py \
      --raw-dir eval/results/final_candidate/null_sweep_same_method/raw \
      --output-dir eval/results/multimodel_ablation \
      --models gemini openai anthropic
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from agent.inference_state import apply_inference_state  # noqa: E402
from agent.output_renderer import render_tool_calls_with_schema  # noqa: E402
from claim_linter import audit_reply  # noqa: E402

load_dotenv(ROOT / ".env")

SYSTEM_PROMPT = (
    "You are the ungoverned ablation of a single-cell analysis assistant. "
    "Answer from the supplied run_deseq2 result. Do not call tools."
)


def canonical_hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def call_gemini(prompt: str, model: str = "gemini-2.5-flash") -> str:
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise SystemExit("GEMINI_API_KEY not set")
    client = genai.Client(api_key=key)
    try:
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0,
                max_output_tokens=800,
            ),
        )
    finally:
        client.close()
    return (resp.text or "").strip()


def call_openai(prompt: str, model: str = "gpt-4o") -> str:
    from openai import OpenAI

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY not set")
    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        max_tokens=800,
    )
    return (resp.choices[0].message.content or "").strip()


def call_anthropic(prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    import anthropic

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=800,
    )
    return resp.content[0].text.strip()


MODEL_CALLERS = {
    "gemini": call_gemini,
    "openai": call_openai,
    "anthropic": call_anthropic,
}


def extract_allocations(raw_json: dict) -> list[dict]:
    return raw_json.get("allocations", raw_json.get("results", []))


def run_one_allocation(alloc: dict, model_name: str, prompt: str) -> dict:
    shared = alloc.get("shared_result", alloc.get("governed", {}).get("tool_result", {}))
    source_hash = canonical_hash(shared)
    tool_args = alloc.get("tool_args", {"cell_type": "unknown"})

    governed = apply_inference_state("run_deseq2", shared, tool_args)
    governed_call = {"name": "run_deseq2", "args": tool_args, "result": governed}
    governed_text, schemas = render_tool_calls_with_schema([governed_call])

    payload = f"USER REQUEST:\n{prompt}\n\nRUN_DESEQ2 RESULT:\n{json.dumps(shared)}"
    caller = MODEL_CALLERS[model_name]
    ungoverned_text = caller(payload)

    raw_call = {"name": "run_deseq2", "args": tool_args, "result": shared}
    gold = {"expect_tools": ["run_deseq2"], "forbid_significance_claim": True}

    return {
        "model": model_name,
        "shared_result_sha256": source_hash,
        "governed": {
            "reply": governed_text,
            "violations": audit_reply(governed_text, [governed_call], gold),
        },
        "ungoverned": {
            "reply": ungoverned_text,
            "violations": audit_reply(ungoverned_text, [raw_call], gold),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-model governance ablation")
    parser.add_argument("--raw-dir", type=Path, required=True,
                        help="Directory with raw same-method JSON files")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=["gemini"],
                        choices=list(MODEL_CALLERS.keys()))
    parser.add_argument("--max-allocations", type=int, default=20,
                        help="Max allocations per model (subset for cost control)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw_files = sorted(args.raw_dir.glob("*.json"))
    if not raw_files:
        raise SystemExit(f"No JSON files in {args.raw_dir}")

    prompt = (
        "Run differential expression between the two groups "
        "and state whether any genes are significant."
    )

    all_allocations = []
    for f in raw_files:
        data = json.loads(f.read_text(encoding="utf-8"))
        tissue = f.stem.split("_governed_")[0].split("_ungoverned_")[0]
        allocs = extract_allocations(data)
        for i, a in enumerate(allocs):
            a["_source_file"] = f.name
            a["_tissue"] = tissue
            a["_index"] = i
            all_allocations.append(a)

    rng = random.Random(args.seed)
    if len(all_allocations) > args.max_allocations:
        all_allocations = rng.sample(all_allocations, args.max_allocations)

    print(f"Running {len(all_allocations)} allocations x {len(args.models)} models")

    for model_name in args.models:
        print(f"\n=== Model: {model_name} ===")
        results = []
        for i, alloc in enumerate(all_allocations):
            print(f"  [{i+1}/{len(all_allocations)}] {alloc['_tissue']}")
            try:
                rec = run_one_allocation(alloc, model_name, prompt)
                rec["tissue"] = alloc["_tissue"]
                rec["allocation_index"] = alloc["_index"]
                results.append(rec)
            except Exception as e:
                print(f"    ERROR: {e}")
                results.append({"error": str(e), "tissue": alloc["_tissue"]})

        outfile = args.output_dir / f"multimodel_{model_name}.json"
        outfile.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

        n_gov_overclaim = sum(
            1 for r in results
            if not r.get("error") and r["governed"]["violations"]
        )
        n_ungov_overclaim = sum(
            1 for r in results
            if not r.get("error") and r["ungoverned"]["violations"]
        )
        n_ok = sum(1 for r in results if not r.get("error"))
        print(f"  Governed overclaim: {n_gov_overclaim}/{n_ok}")
        print(f"  Ungoverned overclaim: {n_ungov_overclaim}/{n_ok}")

    print(f"\nResults saved to {args.output_dir}")


if __name__ == "__main__":
    main()
