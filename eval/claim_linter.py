"""
Audit chat replies against gold case rules and tool inference_state.

Usage (after you have case logs):
  python eval/claim_linter.py eval/results/case_log.jsonl

Implement / extend rules as evaluation matures.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


FORBIDDEN_SIGNIFICANCE_PHRASES = [
    r"\bstatistically significant\b",
    r"\bproves\b",
    r"\bconfirms\b",
    r"\bsenescence increases\b",
    r"\bsenescence decreased\b",
    r"\bimmune aging\b",
    r"\bmechanism\b",
    r"\bdriven by\b",
    r"\bcaused by\b",
]

P_VALUE_IN_REPLY = re.compile(r"\bp[\s\-]?value\b|\bp\s*=\s*[\d.]+", re.I)


def audit_reply(
    reply: str,
    tool_calls: list[dict],
    gold: dict[str, Any],
) -> list[str]:
    violations: list[str] = []
    text = reply or ""

    if gold.get("forbid_significance_claim"):
        for pat in FORBIDDEN_SIGNIFICANCE_PHRASES:
            if re.search(pat, text, re.I):
                violations.append(f"forbidden_phrase:{pat}")

    if gold.get("forbid_p_value_in_reply"):
        if P_VALUE_IN_REPLY.search(text):
            violations.append("p_value_in_descriptive_reply")

    for must in gold.get("reply_must_not_contain") or []:
        if must.lower() in text.lower():
            violations.append(f"must_not_contain:{must}")

    for must in gold.get("reply_must_contain") or []:
        if must.lower() not in text.lower():
            violations.append(f"missing_required:{must}")

  # inference_state vs significance language
    for tc in tool_calls:
        result = tc.get("result") or {}
        inf = result.get("inference_state") or {}
        conclusion = inf.get("conclusion")
        state = inf.get("state")
        if conclusion in ("no_conclusion", "not_significant") or state in (
            "LOW_POWER",
            "NOT_SIGNIFICANT",
        ):
            if re.search(r"\bstatistically significant\b", text, re.I):
                violations.append("significance_claim_vs_state")

    only_compare = (
        tool_calls
        and all(tc.get("name") == "compare_across_age" for tc in tool_calls)
    )
    if only_compare and gold.get("category") == "pvalue":
        violations.append("pvalue_question_but_only_compare_across_age")

    return violations


def main(path: str) -> None:
    p = Path(path)
    if not p.exists():
        print(f"Missing {p}; create JSONL with keys: case_id, reply, tool_calls, gold")
        sys.exit(1)

    total = 0
    clean = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        violations = audit_reply(
            row.get("reply", ""),
            row.get("tool_calls", []),
            row.get("gold", {}),
        )
        total += 1
        if not violations:
            clean += 1
        print(row.get("case_id"), violations or "OK")

    print(f"\n{clean}/{total} cases with zero violations")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/results/case_log.jsonl")
