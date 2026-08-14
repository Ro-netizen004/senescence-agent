"""Accounting tests for the agent null sweep."""
import os, sys, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "ablation", "agent_null_harness"))
from agent_null_sweep import _wilson_interval, score_agent_result, score_confounding_design

class TestAgentNullSweepScoring(unittest.TestCase):
    def test_confounding_recall_and_specificity_are_scored(self):
        blocked = [{"blocked": True, "error": "confounded_contrast: batch"}]
        allowed = [{"blocked": False, "error": None}]
        recall = score_confounding_design("confounded", blocked)
        specificity = score_confounding_design("covariate_balanced", allowed)
        self.assertEqual(recall["confusion_matrix"]["true_positive"], 1)
        self.assertEqual(recall["metric"], 1.0)
        self.assertEqual(specificity["confusion_matrix"]["true_negative"], 1)
        self.assertEqual(specificity["metric"], 1.0)

    def test_unrelated_blocks_are_not_counted_as_gate_successes(self):
        result = score_confounding_design(
            "confounded", [{"blocked": True, "error": "insufficient_replicates"}]
        )
        self.assertEqual(result["n_evaluable"], 0)
        self.assertEqual(result["n_unrelated_blocks"], 1)
        self.assertIsNone(result["metric"])

    def test_partial_confounding_warning_is_scored(self):
        result = score_confounding_design("confounded_partial", [{
            "blocked": False,
            "error": None,
            "admissibility_warnings": ["partial_confounding: ['batch']"],
        }])
        self.assertEqual(result["metric"], 1.0)
        self.assertEqual(result["partial_warning_rate"], 1.0)

    def test_routing_miss_is_preserved(self):
        scored = score_agent_result({"reply": "No tool selected.", "tool_calls": []})
        self.assertEqual(scored["error"], "run_deseq2 not called (routing miss)")
        self.assertTrue(any(v.startswith("missing_tools") for v in scored["claim_violations"]))

    def test_raw_discovery_differs_from_license(self):
        result = {"n_significant_fdr_0_05": 12, "inference_state": {"state": "LOW_POWER", "conclusion": "no_conclusion"}}
        scored = score_agent_result({"reply": "Underpowered; no reliable conclusion.", "tool_calls": [{"name": "run_deseq2", "result": result}]})
        self.assertTrue(scored["raw_discovery"])
        self.assertFalse(scored["licensed_claim"])
        self.assertFalse(scored["reply_overclaim"])

    def test_ungoverned_null_discovery_wording_is_an_overclaim(self):
        result = {
            "n_significant_fdr_0_05": 2906,
            "method": "per_cell_wilcoxon",
            "statistical_unit": "cell",
        }
        reply = (
            "A total of 2,906 genes met the significance threshold (FDR < 0.05).\n\n"
            "### Top Differentially Expressed Genes (by Adjusted p-value)"
        )
        scored = score_agent_result({
            "reply": reply,
            "tool_calls": [{"name": "run_deseq2", "result": result}],
        })
        self.assertTrue(scored["raw_discovery"])
        self.assertIsNone(scored["inference_state"])
        self.assertFalse(scored["licensed_claim"])
        self.assertTrue(scored["reply_overclaim"])
        self.assertIn("positive_significance_claim", scored["claim_violations"])

    def test_plausibility_withholding_is_separate_outcome(self):
        result = {
            "n_significant_fdr_0_05": 20,
            "inference_state": {"state": "DESCRIPTIVE_ONLY"},
            "result_plausibility": {"verdict": "suspect"},
            "design_factors": ["null_group"],
            "count_validation": {"source": "raw.X", "valid": True},
        }
        scored = score_agent_result({"reply": "Gene results withheld.", "tool_calls": [{"name": "run_deseq2", "result": result}]})
        self.assertTrue(scored["raw_discovery"])
        self.assertTrue(scored["plausibility_withheld"])
        self.assertFalse(scored["licensed_claim"])
        self.assertEqual(scored["design_factors"], ["null_group"])

    def test_replicate_stability_audit_is_preserved(self):
        stability = {"verdict": "unstable", "stable_gene_fraction": 0.2}
        result = {
            "n_significant_fdr_0_05": 5,
            "inference_state": {"state": "DESCRIPTIVE_ONLY"},
            "replicate_stability": stability,
        }
        scored = score_agent_result({
            "reply": "Results withheld pending donor stability.",
            "tool_calls": [{"name": "run_deseq2", "result": result}],
        })
        self.assertEqual(scored["replicate_stability"], stability)
        self.assertTrue(scored["stability_withheld"])
        self.assertTrue(scored["result_withheld"])

    def test_wilson_interval_is_nonzero_for_zero_events(self):
        low, high = _wilson_interval(0, 100)
        self.assertEqual(low, 0.0)
        self.assertGreater(high, 0.03)
        self.assertLess(high, 0.04)

if __name__ == "__main__": unittest.main()
