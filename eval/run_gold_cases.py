"""
Run gold benchmark cases through run_agent and append results to JSONL.

Requires: GEMINI_API_KEY in repo-root .env, kidney h5ad uploaded, file_id in dataset_manifest.yaml

Examples:
  cd backend
  ..\\venv\\Scripts\\python.exe ..\\eval\\run_gold_cases.py --day1
  ..\\venv\\Scripts\\python.exe ..\\eval\\run_gold_cases.py --all
  ..\\venv\\Scripts\\python.exe ..\\eval\\run_gold_cases.py --id pvalue_tcell_3m_24m
  ..\\venv\\Scripts\\python.exe ..\\eval\\run_gold_cases.py --day1 --dry-run

Panel case uses 0 Gemini calls; multistep may use 2-5 calls (excluded from --day1).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Load .env before agent imports
from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

import yaml  # pip install pyyaml

from agent.agent import run_agent

# 20 cases = all gold cases except panel (no API) and multistep (extra API)
DAY1_SKIP_IDS = {"panel_run_everything", "multistep_score_then_test"}


def load_manifest() -> dict:
    path = EVAL_DIR / "dataset_manifest.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("datasets", {}).get("kidney_tms", {})


def load_gold_cases() -> list[dict]:
    path = EVAL_DIR / "gold_cases.yaml"
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("cases", [])


def select_cases(
    cases: list[dict],
    *,
    day1: bool,
    all_cases: bool,
    case_id: str | None,
    limit: int | None,
) -> list[dict]:
    if case_id:
        matched = [c for c in cases if c.get("id") == case_id]
        if not matched:
            raise SystemExit(f"Unknown case id: {case_id}")
        return matched

    if all_cases:
        selected = cases
    elif day1:
        selected = [c for c in cases if c.get("id") not in DAY1_SKIP_IDS]
    else:
        raise SystemExit("Specify --day1, --all, or --id")

    if limit is not None:
        selected = selected[:limit]
    return selected


def _retry_seconds_from_error(exc: Exception) -> float:
    msg = str(exc)
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", msg, re.I)
    if m:
        return float(m.group(1)) + 2.0
    if "429" in msg or "quota" in msg.lower():
        return 30.0
    return 0.0


def run_one(
    case: dict,
    file_id: str,
    species: str,
    *,
    max_retries: int = 5,
) -> dict:
    message = case["message"]
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            result = run_agent(
                session_history=[],
                message=message,
                file_id=file_id,
                species=species,
            )
            break
        except Exception as exc:
            last_exc = exc
            wait = _retry_seconds_from_error(exc)
            if wait <= 0 or attempt >= max_retries:
                raise
            print(f"  Retry {attempt + 1}/{max_retries} after {wait:.0f}s ({exc})")
            time.sleep(wait)
    else:
        raise last_exc  # type: ignore[misc]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_id": case.get("id"),
        "category": case.get("category"),
        "message": message,
        "file_id": file_id,
        "species": species,
        "reply": result.get("reply", ""),
        "tool_calls": result.get("tool_calls", []),
        "plots": result.get("plots", []),
        "gold": case,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run eval gold cases via run_agent")
    parser.add_argument("--day1", action="store_true", help="20 API cases (skip panel + multistep)")
    parser.add_argument("--all", action="store_true", help="All cases in gold_cases.yaml")
    parser.add_argument("--id", dest="case_id", help="Single case id")
    parser.add_argument("--file-id", help="Override file_id from dataset_manifest.yaml")
    parser.add_argument("--species", default=None, help="Default from manifest (mouse)")
    parser.add_argument(
        "--output",
        default=str(EVAL_DIR / "results" / "run_log.jsonl"),
        help="Append results JSONL path",
    )
    parser.add_argument("--dry-run", action="store_true", help="List cases only, no API calls")
    parser.add_argument("--limit", type=int, default=None, help="Max cases to run")
    parser.add_argument(
        "--delay",
        type=float,
        default=13.0,
        help="Seconds between cases (free tier: 5 req/min → use >=12)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace output file instead of appending",
    )
    args = parser.parse_args()

    if not args.day1 and not args.all and not args.case_id:
        parser.error("Use --day1, --all, or --id")

    manifest = load_manifest()
    file_id = args.file_id or manifest.get("file_id") or ""
    species = args.species or manifest.get("species") or "mouse"

    if not args.dry_run and not file_id:
        raise SystemExit(
            "file_id is empty. Upload h5ad via UI, then set eval/dataset_manifest.yaml "
            "or pass --file-id YOUR_UUID"
        )

    cases = load_gold_cases()
    selected = select_cases(
        cases,
        day1=args.day1,
        all_cases=args.all,
        case_id=args.case_id,
        limit=args.limit,
    )

    print(f"Selected {len(selected)} case(s)")
    if args.dry_run:
        for i, c in enumerate(selected, 1):
            skip = "(0 API)" if c.get("id") in DAY1_SKIP_IDS else "(~1+ API)"
            print(f"  {i}. {c.get('id')}: {c.get('message', '')[:70]}... {skip}")
        return

    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY not set in .env")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if args.overwrite and out_path.exists():
        out_path.write_text("", encoding="utf-8")

    for i, case in enumerate(selected, 1):
        if i > 1 and args.delay > 0:
            print(f"  Waiting {args.delay:.0f}s (rate limit spacing)...")
            time.sleep(args.delay)
        cid = case.get("id")
        print(f"\n[{i}/{len(selected)}] {cid}")
        print(f"  Q: {case.get('message')}")
        try:
            row = run_one(case, file_id, species, max_retries=5)
            tools = [t.get("name") for t in row.get("tool_calls", [])]
            print(f"  Tools: {tools}")
            print(f"  Reply preview: {row.get('reply', '')[:120]}...")
        except Exception as e:
            row = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "case_id": cid,
                "error": str(e),
                "gold": case,
            }
            print(f"  ERROR: {e}")

        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")

    print(f"\nDone. Appended to {out_path}")
    print(f"Next: python eval/claim_linter.py {out_path}")


if __name__ == "__main__":
    main()
