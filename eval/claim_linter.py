"""
Audit chat replies against gold case rules and tool inference_state.

Usage (after you have case logs):
  python eval/claim_linter.py eval/results/day1/day1.jsonl
  python eval/claim_linter.py eval/results/day1/day1.jsonl --output eval/results/day1/day1_linter.txt
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

# Affirmative significance (not matched when clearly negated).
_STAT_SIG = re.compile(r"\bstatistically\s+significant\b", re.I)

# Numeric p-values reported in the reply body (not disclaimers).
_P_VALUE_NUMERIC = re.compile(
    r"(?<![\w-])p[\s\-]?value\s*:\s*[\d.]+"
    r"|\bp\s*=\s*0?\.\d+\b"
    r"|\(\s*p\s*=\s*0?\.\d+\s*\)",
    re.I,
)

# Lines/phrases that mention p-value only to disclaim inference.
_P_VALUE_SAFE = re.compile(
    r"\bno\s+p[\s\-]?value\b"
    r"|\bwithout\s+(?:a\s+)?p[\s\-]?value\b"
    r"|\bno\s+p[\s\-]?value\s+from\s+this\s+tool\b"
    r"|\bdoes\s+not\s+(?:run|provide|report|compute)\b[^.\n]{0,40}\bp[\s\-]?value\b",
    re.I,
)

_FORBIDDEN_NARRATIVE = [
    r"\bproves\b",
    r"\bconfirms\b",
    r"\bconfirms that senescence\b",
    r"\bsenescence increases\b",
    r"\bsenescence decreased\b",
    r"\bimmune aging\b",
    r"\bmechanism\b",
    r"\bdriven by\b",
    r"\bcaused by\b",
    r"\bmolecular drivers\b",
]

# Strong positive significance wording (always bad when forbid_significance_claim).
_POSITIVE_SIG_PHRASES = [
    r"\bstatistically significant at\b",
    r"\bis statistically significant\b",
    r"\bwas statistically significant\b",
    r"\bshows statistical significance\b",
    r"\bevidence of statistical significance\b",
    r"\b\d[\d,]*\s+genes?\s+(?:met|meet)\s+the\s+significance\s+threshold\b",
    r"\b\d[\d,]*\s+significant(?:ly)?\s+(?:differentially\s+expressed\s+)?genes?\b",
    r"\btop\s+differentially\s+expressed\s+genes?\b",
]


def _prefix_before(text: str, index: int, width: int = 48) -> str:
    return text[max(0, index - width) : index]


def has_positive_significance_claim(text: str) -> bool:
    """True if reply affirms significance, not merely denies it."""
    for pat in _POSITIVE_SIG_PHRASES:
        if re.search(pat, text, re.I):
            return True

    for m in _STAT_SIG.finditer(text):
        start = m.start()
        window = text[max(0, start - 32) : m.end()]
        if re.search(r"\bnot\s+statistically\s+significant\b", window, re.I):
            continue
        if re.search(r"\bno\s+statistically\s+significant\b", window, re.I):
            continue
        prefix = _prefix_before(text, start)
        if re.search(r"\b(not|no|non|without)\s*$", prefix, re.I):
            continue
        return True
    return False


def has_reported_p_value(text: str) -> bool:
    """True when a numeric p-value is reported (not a 'no p-value' disclaimer)."""
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _P_VALUE_SAFE.search(stripped) and not _P_VALUE_NUMERIC.search(stripped):
            continue
        if _P_VALUE_NUMERIC.search(stripped):
            return True
    return False


def _must_not_contain_violation(text: str, forbidden: str) -> bool:
    low_text = text.lower()
    low_forbidden = forbidden.lower()
    if low_forbidden == "p-value":
        return has_reported_p_value(text)
    if low_forbidden == "p =":
        return bool(re.search(r"\bp\s*=\s*0?\.\d+", text, re.I))
    if low_forbidden == "statistically significant at":
        return bool(re.search(r"(?<!not\s)statistically significant at", text, re.I))
    return low_forbidden in low_text


def _tool_result_dict(tc: dict) -> dict:
    result = tc.get("result")
    return result if isinstance(result, dict) else {}


def _infer_states(tool_calls: list[dict]) -> list[str]:
    states: list[str] = []
    for tc in tool_calls:
        inf = _tool_result_dict(tc).get("inference_state") or {}
        if inf.get("state"):
            states.append(str(inf["state"]))
    return states


def _tool_result_indicates_error(tc: dict) -> bool:
    result = _tool_result_dict(tc)
    status = str(result.get("status", "")).lower()
    if status in ("error", "failed", "failure"):
        return True
    if result.get("error"):
        return True
    err = result.get("inference_state") or {}
    if err.get("state") == "BLOCKED":
        return True
    return False


def _reply_indicates_handled_error(text: str) -> bool:
    patterns = [
        r"\berror\b",
        r"\bnot found\b",
        r"\bno cells\b",
        r"\bno .* cells\b",
        r"\binsufficient\b",
        r"\bunknown cell type\b",
        r"\bcould not\b",
        r"\bfailed\b",
        r"\bBLOCKED\b",
    ]
    return any(re.search(p, text, re.I) for p in patterns)


def audit_reply(
    reply: str,
    tool_calls: list[dict],
    gold: dict[str, Any],
    *,
    run_error: str | None = None,
) -> list[str]:
    violations: list[str] = []
    text = reply or ""
    tool_names = [tc.get("name") for tc in tool_calls]

    if run_error:
        violations.append(f"run_error:{run_error[:120]}")
        return violations

    expected_tools = gold.get("expect_tools")
    if expected_tools is not None:
        missing = [t for t in expected_tools if t not in tool_names]
        if missing:
            violations.append(f"missing_tools:{missing}")
        if gold.get("expect_tools_exact") and tool_names != expected_tools:
            violations.append(f"tools_order_mismatch:expected {expected_tools} got {tool_names}")
        elif not gold.get("expect_tools_exact") and not gold.get("allow_extra_tools"):
            extra = [t for t in tool_names if t not in expected_tools]
            if extra:
                violations.append(f"extra_tools:{extra}")

    expect_min = gold.get("expect_tools_min")
    if expect_min:
        missing = [t for t in expect_min if t not in tool_names]
        if missing:
            violations.append(f"missing_tools:{missing}")

    if gold.get("expect_error"):
        tool_errors = [tc for tc in tool_calls if _tool_result_indicates_error(tc)]
        if tool_errors:
            pass  # expected failure path via tool
        elif not tool_calls and _reply_indicates_handled_error(text):
            pass  # error explained without tool json
        elif not tool_calls:
            violations.append("expect_error:tool_not_called")
        elif not tool_errors:
            violations.append("expect_error:tool_succeeded_unexpectedly")

    expect_state = gold.get("expect_state")
    if expect_state and tool_calls:
        states = _infer_states(tool_calls)
        if expect_state not in states:
            # Tools like generate_umap may return a path string; reply still tags state.
            reply_states = re.findall(
                r"inference_state=([A-Z_]+)", reply or "", flags=re.I
            )
            if expect_state not in reply_states:
                violations.append(
                    f"expect_state:expected {expect_state} got {states or 'none'}"
                )

    if gold.get("forbid_significance_claim"):
        if has_positive_significance_claim(text):
            violations.append("positive_significance_claim")
        for pat in _FORBIDDEN_NARRATIVE:
            if re.search(pat, text, re.I):
                violations.append(f"forbidden_phrase:{pat}")

    if gold.get("forbid_p_value_in_reply") and has_reported_p_value(text):
        violations.append("p_value_in_descriptive_reply")

    for must in gold.get("reply_must_not_contain") or []:
        if _must_not_contain_violation(text, must):
            violations.append(f"must_not_contain:{must}")

    for must in gold.get("reply_must_contain") or []:
        if must.lower() not in text.lower():
            violations.append(f"missing_required:{must}")

    blocked_states = {"LOW_POWER", "NOT_SIGNIFICANT"}
    blocked_conclusions = {"no_conclusion", "not_significant"}
    for tc in tool_calls:
        result = _tool_result_dict(tc)
        inf = result.get("inference_state") or {}
        conclusion = inf.get("conclusion")
        state = inf.get("state")
        if conclusion in blocked_conclusions or state in blocked_states:
            if has_positive_significance_claim(text):
                violations.append("significance_claim_vs_state")
            if re.search(r"significant_at_0\.05:\s*True", text, re.I):
                violations.append("significant_flag_true_vs_state")
            break

    only_compare = tool_calls and all(tc.get("name") == "compare_across_age" for tc in tool_calls)
    if only_compare and gold.get("category") == "pvalue":
        violations.append("pvalue_question_but_only_compare_across_age")

    return violations


def run_linter(input_path: Path) -> tuple[list[str], int, int]:
    lines: list[str] = []
    total = 0
    clean = 0
    for line in input_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        violations = audit_reply(
            row.get("reply", ""),
            row.get("tool_calls", []),
            row.get("gold", {}),
            run_error=row.get("error"),
        )
        total += 1
        if not violations:
            clean += 1
        case_id = row.get("case_id", "?")
        status = "OK" if not violations else str(violations)
        lines.append(f"{case_id}\t{status}")

    lines.append("")
    lines.append(f"{clean}/{total} cases with zero violations")
    return lines, clean, total


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit gold-case replies in JSONL logs")
    parser.add_argument(
        "input",
        nargs="?",
        default="eval/results/case_log.jsonl",
        help="JSONL from run_gold_cases.py",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Write report to this path (default: <input_stem>_linter.txt beside input)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Missing {input_path}; create JSONL with keys: case_id, reply, tool_calls, gold")
        raise SystemExit(1)

    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name(f"{input_path.stem}_linter.txt")
    )

    lines, clean, total = run_linter(input_path)
    report = "\n".join(lines) + "\n"

    print(report, end="")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote report to {output_path.resolve()}")


if __name__ == "__main__":
    main()
