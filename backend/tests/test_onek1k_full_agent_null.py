import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "eval/external_validation/onek1k/full_agent_null.py"
SPEC = importlib.util.spec_from_file_location("onek1k_full_agent_null", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_null_score_accepts_correct_zero_discovery_reply():
    response = {
        "reply": "No statistically significant genes were found at FDR < 0.05.",
        "tool_calls": [{
            "name": "run_deseq2",
            "args": {
                "group_column": "null_group",
                "reference_group": "fake_A",
                "comparison_group": "fake_B",
            },
            "result": {
                "n_significant_fdr_0_05": 0,
                "covariates_used": ["pool", "sex", "age"],
                "results": [],
                "inference_state": {"state": "NOT_SIGNIFICANT"},
            },
        }],
    }
    score = MODULE.score_response(response, {"allocation_id": "x", "n_discoveries": 0})
    assert score["routing_success"] is True
    assert score["communicates_no_significant_result"] is True
    assert score["positive_significance_claim"] is False


def test_null_score_rejects_positive_claim():
    response = {
        "reply": "One gene is statistically significant.",
        "tool_calls": [{
            "name": "run_deseq2",
            "args": {
                "group_column": "null_group",
                "reference_group": "fake_A",
                "comparison_group": "fake_B",
            },
            "result": {
                "n_significant_fdr_0_05": 0,
                "covariates_used": ["pool", "sex", "age"],
                "results": [],
            },
        }],
    }
    score = MODULE.score_response(response, {"allocation_id": "x", "n_discoveries": 0})
    assert score["communicates_no_significant_result"] is False
    assert score["positive_significance_claim"] is True


def test_null_score_accepts_governed_renderer_wording():
    response = {
        "reply": "**No genes** passed FDR < 0.05 for Mono C.",
        "tool_calls": [{
            "name": "run_deseq2",
            "args": {
                "group_column": "null_group",
                "reference_group": "fake_A",
                "comparison_group": "fake_B",
            },
            "result": {
                "n_significant_fdr_0_05": 0,
                "covariates_used": ["pool", "sex", "age"],
                "results": [],
                "inference_state": {"state": "NOT_SIGNIFICANT"},
            },
        }],
    }
    score = MODULE.score_response(response, {"allocation_id": "x", "n_discoveries": 0})
    assert score["communicates_no_significant_result"] is True

def test_null_score_accepts_structured_zero_counts():
    replies = [
        '"n_significant_fdr_0_05": 0',
        "**Significant Genes (FDR < 0.05):** 0",
        "- **Significant Genes (FDR < 0.05)**: 0",
    ]
    for reply in replies:
        response = {
            "reply": reply,
            "tool_calls": [{
                "name": "run_deseq2",
                "args": {
                    "group_column": "null_group",
                    "reference_group": "fake_A",
                    "comparison_group": "fake_B",
                },
                "result": {
                    "n_significant_fdr_0_05": 0,
                    "covariates_used": ["pool", "sex", "age"],
                    "results": [],
                },
            }],
        }
        score = MODULE.score_response(response, {"allocation_id": "x", "n_discoveries": 0})
        assert score["communicates_no_significant_result"] is True
        assert score["positive_significance_claim"] is False
