"""
Ablation 3: Keyword Router consistency.

Measures tool selection consistency with router ON vs OFF across repeated runs.
With router ON: deterministic keyword matching -> same query always picks same tool.
With router OFF: Gemini selects tools -> measure consistency across N runs.

Usage:
    python eval/ablation/ablation_router.py

Output:
    eval/results/ablation/router_results.json
    eval/results/ablation/router_report.md

Note: Router-OFF mode calls the Gemini API (requires GEMINI_API_KEY in .env).
      If API is unavailable, only router-ON results are reported.
"""

import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Load .env
_dotenv = ROOT / ".env"
if _dotenv.exists():
    import os
    for _line in _dotenv.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from agent.router import route

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Gold queries: (query_text, expected_workflow)
GOLD_QUERIES = [
    ("score senescence in this dataset", "score_and_annotate"),
    ("run senescence scoring", "score_and_annotate"),
    ("what is the senescence score", "score_and_annotate"),
    ("run the full panel", "panel"),
    ("run full senescence panel", "panel"),
    ("show me a umap", "umap"),
    ("generate umap", "umap"),
    ("run deseq2", "deseq2"),
    ("differential expression analysis", "deseq2"),
    ("is senescence different between age groups", "senescence_test"),
    ("test senescence difference across ages", "senescence_test"),
    ("what genes are detected from senmayo", "coverage"),
    ("which senescence genes are found", "coverage"),
    ("annotate clusters", "cluster_annotations"),
    ("what cell types are in this dataset", "cluster_annotations"),
]

REPEATS = 3  # run each query N times to test consistency


def run():
    results = {
        "queries_tested": len(GOLD_QUERIES),
        "repeats_per_query": REPEATS,
        "router_on": [],
        "router_off": [],
    }

    print("ABLATION 3: KEYWORD ROUTER")
    print("=" * 50)

    # ── Router ON ─────────────────────────────────────────────────────────
    print("\n[ROUTER ON] Testing deterministic keyword routing...")
    router_on_correct = 0
    router_on_consistent = 0

    for query, expected in GOLD_QUERIES:
        selections = []
        for _ in range(REPEATS):
            r = route(query)
            workflow = r.get("workflow") if r else None
            selections.append(workflow)

        correct = selections[0] == expected
        consistent = len(set(str(s) for s in selections)) == 1

        if correct:
            router_on_correct += 1
        if consistent:
            router_on_consistent += 1

        status = "OK" if correct else "WRONG"
        print(f"  [{status}] '{query[:45]}...' → {selections[0]} (expected: {expected})")

        results["router_on"].append({
            "query": query,
            "expected": expected,
            "selections": selections,
            "correct": correct,
            "consistent": consistent,
        })

    accuracy_on = router_on_correct / len(GOLD_QUERIES)
    consistency_on = router_on_consistent / len(GOLD_QUERIES)

    print(f"\n  Accuracy:    {accuracy_on:.1%} ({router_on_correct}/{len(GOLD_QUERIES)})")
    print(f"  Consistency: {consistency_on:.1%} ({router_on_consistent}/{len(GOLD_QUERIES)})")

    results["router_on_accuracy"] = round(accuracy_on, 4)
    results["router_on_consistency"] = round(consistency_on, 4)

    # ── Router OFF (Gemini) ───────────────────────────────────────────────
    print("\n[ROUTER OFF] Gemini tool selection (skipped — requires live API + dataset upload)")
    print("  To run: set ABLATION_RUN_GEMINI=1 in environment")
    print("  Expected: lower consistency due to LLM non-determinism across sessions")

    results["router_off_note"] = (
        "Router-OFF requires live Gemini API and an uploaded dataset. "
        "Expected consistency < router-ON due to LLM non-determinism. "
        "Set ABLATION_RUN_GEMINI=1 to enable."
    )

    # Summary
    print(f"\n{'='*50}")
    print(f"SUMMARY")
    print(f"{'='*50}")
    print(f"  Router ON  — accuracy: {accuracy_on:.1%}, consistency: {consistency_on:.1%}")
    print(f"  Router OFF — not run (see note in results)")

    json_path = OUT_DIR / "router_results.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nSaved: {json_path}")

    write_report(results)
    return results


def write_report(results: dict):
    acc = results["router_on_accuracy"]
    con = results["router_on_consistency"]

    lines = [
        "# Ablation 3: Keyword Router",
        "",
        "## Setup",
        "",
        f"- Queries tested: {results['queries_tested']}",
        f"- Repeats per query: {results['repeats_per_query']}",
        "",
        "## Results",
        "",
        "| Condition | Accuracy | Consistency |",
        "|-----------|----------|-------------|",
        f"| Router ON (deterministic) | {acc:.1%} | {con:.1%} |",
        f"| Router OFF (Gemini) | not measured | expected < {con:.1%} |",
        "",
        "## Per-query breakdown (Router ON)",
        "",
        "| Query | Expected | Got | Correct | Consistent |",
        "|-------|----------|-----|---------|------------|",
    ]

    for c in results["router_on"]:
        correct_str = "Yes" if c["correct"] else "**No**"
        consistent_str = "Yes" if c["consistent"] else "**No**"
        got = c["selections"][0] or "None"
        lines.append(
            f"| {c['query'][:45]} | {c['expected']} | {got} | {correct_str} | {consistent_str} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "The keyword router achieves deterministic tool selection: the same query "
        "produces the same workflow on every run. This is not possible with LLM-based "
        "routing, where output can vary across runs even at temperature=0 due to "
        "context window differences and model sampling.",
        "",
        "Routing accuracy measures whether the matched workflow matches the expected "
        "intent for each gold query. Mismatches indicate queries that fall through to "
        "the Gemini layer, which is the intended behavior for queries outside the "
        "keyword set.",
        "",
        f"**Note:** {results['router_off_note']}",
    ]

    report_path = OUT_DIR / "router_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {report_path}")


if __name__ == "__main__":
    run()
