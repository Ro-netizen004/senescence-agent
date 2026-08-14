"""Unit tests for eval/claim_linter.py — run: python -m unittest eval.test_claim_linter"""

from __future__ import annotations

import unittest

from eval.claim_linter import (
    audit_reply,
    has_positive_significance_claim,
    has_reported_p_value,
)


class TestSignificanceDetection(unittest.TestCase):
    def test_allows_negated_significance(self):
        self.assertFalse(
            has_positive_significance_claim(
                "not statistically significant (p=0.6095)."
            )
        )
        self.assertFalse(
            has_positive_significance_claim(
                "No statistically reliable difference detected."
            )
        )

    def test_catches_positive_significance(self):
        self.assertTrue(
            has_positive_significance_claim(
                "Senescence is statistically significant at alpha=0.05."
            )
        )
        self.assertTrue(
            has_positive_significance_claim(
                "The result is statistically significant."
            )
        )

    def test_allows_withheld_diagnostic_significant_gene_count(self):
        reply = (
            "17/43 significant genes have |log2FC| > 8. "
            "Gene-level results were withheld because the output failed the "
            "result-plausibility gate."
        )
        self.assertFalse(has_positive_significance_claim(reply))

    def test_catches_threshold_claim_and_ranked_de_heading(self):
        reply = (
            "A total of 2,906 genes met the significance threshold. "
            "Top Differentially Expressed Genes (by adjusted p-value)"
        )
        self.assertTrue(has_positive_significance_claim(reply))


class TestPValueDetection(unittest.TestCase):
    def test_allows_disclaimer(self):
        self.assertFalse(
            has_reported_p_value(
                "Age-stratified SenMayo scores (descriptive only; no p-value from this tool)."
            )
        )

    def test_catches_numeric_p_value(self):
        self.assertTrue(has_reported_p_value("p-value: 0.4857"))
        self.assertTrue(has_reported_p_value("Difference (p=0.03) was found."))


class TestAuditReply(unittest.TestCase):
    def test_descriptive_compare_ok(self):
        reply = (
            "Age comparison (descriptive only).\n\n"
            "Age-stratified SenMayo scores (descriptive only; no p-value from this tool).\n"
            "Median scores by age: {'3m': 30.1}\n"
        )
        gold = {
            "category": "descriptive",
            "expect_tools": ["compare_across_age"],
            "expect_state": "DESCRIPTIVE_ONLY",
            "forbid_p_value_in_reply": True,
            "reply_must_not_contain": ["p-value", "p ="],
        }
        tool_calls = [
            {
                "name": "compare_across_age",
                "result": {"inference_state": {"state": "DESCRIPTIVE_ONLY"}},
            }
        ]
        self.assertEqual(audit_reply(reply, tool_calls, gold), [])

    def test_not_significant_pvalue_ok(self):
        reply = (
            "Senescence score test: not statistically significant (p=0.6095).\n"
            "p-value: 0.6095\nsignificant_at_0.05: False\n"
        )
        gold = {"forbid_significance_claim": True}
        tool_calls = [
            {
                "name": "test_senescence_difference",
                "result": {
                    "inference_state": {
                        "state": "NOT_SIGNIFICANT",
                        "conclusion": "not_significant",
                    }
                },
            }
        ]
        self.assertEqual(audit_reply(reply, tool_calls, gold), [])

    def test_false_significance_vs_state(self):
        reply = "The increase is statistically significant at alpha=0.05."
        tool_calls = [
            {
                "name": "test_senescence_difference",
                "result": {
                    "inference_state": {
                        "state": "LOW_POWER",
                        "conclusion": "no_conclusion",
                    }
                },
            }
        ]
        v = audit_reply(reply, tool_calls, {"forbid_significance_claim": True})
        self.assertIn("positive_significance_claim", v)
        self.assertIn("significance_claim_vs_state", v)

    def test_descriptive_with_sneaky_p_value(self):
        reply = "Medians by age. p-value: 0.04 from a quick test."
        gold = {"forbid_p_value_in_reply": True, "category": "descriptive"}
        self.assertIn("p_value_in_descriptive_reply", audit_reply(reply, [], gold))

    def test_wrong_tool_for_pvalue_question(self):
        gold = {"category": "pvalue"}
        tool_calls = [{"name": "compare_across_age", "result": {}}]
        self.assertIn(
            "pvalue_question_but_only_compare_across_age",
            audit_reply("descriptive medians", tool_calls, gold),
        )

    def test_missing_tools(self):
        gold = {"expect_tools": ["test_senescence_difference"]}
        tool_calls = [{"name": "compare_across_age", "result": {}}]
        self.assertIn("missing_tools", audit_reply("x", tool_calls, gold)[0])

    def test_extra_tools_flagged(self):
        gold = {"expect_tools": ["senescence_score"]}
        tool_calls = [
            {"name": "senescence_score", "result": {}},
            {"name": "get_cluster_annotations", "result": {}},
        ]
        self.assertIn("extra_tools", audit_reply("x", tool_calls, gold)[0])

    def test_run_error_short_circuits(self):
        v = audit_reply("", [], {}, run_error="429 quota exceeded")
        self.assertTrue(v[0].startswith("run_error:"))

    def test_expect_error_via_tool_status(self):
        gold = {"expect_error": True, "expect_tools": ["run_deseq2"]}
        tool_calls = [
            {"name": "run_deseq2", "result": {"status": "error", "error": "unknown cell type"}}
        ]
        self.assertEqual(audit_reply("failed", tool_calls, gold), [])


if __name__ == "__main__":
    unittest.main()
