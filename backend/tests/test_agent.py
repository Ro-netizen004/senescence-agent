import os
import sys

# ── make backend importable ─────────────────────────────
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

from agent.agent import run_agent
from agent.cache import get_adata

from tools.visualization import generate_umap
from tools.senescence import find_senescence_markers, senescence_score
from tools.age_analysis import compare_across_age


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def print_result(label, result):
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)

    print("\nReply:\n", result.get("reply"))

    tool_calls = result.get("tool_calls", [])
    print("\nTools called:")
    for t in tool_calls:
        print(f" - {t.get('name')}")

    print("\nPlots:")
    for p in result.get("plots", []):
        print(f" - {p.get('url')} ({p.get('caption')})")


# ─────────────────────────────────────────────
# Agent tests (E2E)
# ─────────────────────────────────────────────

def run_test_1():
    return run_agent(
        session_history=[],
        message="Find the senescent cells in this dataset",
        file_id="test-kidney-001",
        species="mouse"
    )


def run_test_2():
    return run_agent(
        session_history=[],
        message="How do kidney cells change between young and old mice?",
        file_id="test-kidney-001",
        species="mouse"
    )


# ─────────────────────────────────────────────
# Direct tool tests (unit-level)
# ─────────────────────────────────────────────

def run_tool_tests(file_id="test-kidney-001"):
    print("\n" + "=" * 60)
    print("INDIVIDUAL TOOL TESTS")
    print("=" * 60)

    adata = get_adata(file_id)

    if adata is None:
        print("No cached dataset found — run agent first")
        return

    # ── UMAP ─────────────────────────────
    print("\n[generate_umap]")
    try:
        print(generate_umap(adata))
    except Exception as e:
        print("UMAP failed:", e)

    # ── markers ──────────────────────────
    print("\n[find_senescence_markers]")
    try:
        print(find_senescence_markers(adata, "mouse"))
    except Exception as e:
        print("Markers failed:", e)

    # ── score ─────────────────────────────
    print("\n[senescence_score]")
    try:
        print(senescence_score(adata, "mouse"))
    except Exception as e:
        print("Score failed:", e)

    # ── age comparison ────────────────────
    print("\n[compare_across_age]")
    try:
        print(compare_across_age(adata))
    except Exception as e:
        print("Age comparison failed:", e)


# ─────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────

if __name__ == "__main__":

    try:
        # E2E tests
        result1 = run_test_1()
        print_result("TEST 1 - Senescent Cells", result1)

        result2 = run_test_2()
        print_result("TEST 2 - Age Comparison", result2)

        # Unit tests
        run_tool_tests()

        print("\n✅ ALL TESTS COMPLETED")

    except Exception as e:
        print("\n❌ TEST FAILED")
        print("Error:", str(e))
        raise