import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.inference_state import (
    InferenceState,
    InterpretationLevel,
    assign_inference_state,
    build_state_record,
    _deseq2_low_power,
    apply_inference_state,
)


class TestDeseq2InferenceState(unittest.TestCase):
    def test_unstable_replicate_effect_downgrades_significant_result(self):
        result = {
            "n_significant_fdr_0_05": 4,
            "n_samples": 8,
            "samples_per_age": {"A": 4, "B": 4},
            "results": [{"gene": "X", "padj": 0.01}],
            "result_plausibility": {"verdict": "ok"},
            "replicate_stability": {"verdict": "unstable"},
        }
        self.assertEqual(
            assign_inference_state("run_deseq2", result),
            InferenceState.DESCRIPTIVE_ONLY,
        )
        record = build_state_record("run_deseq2", result)
        self.assertIn("replicate_instability", record["validity_flags"])
        self.assertFalse(record["validity_gate_passed"])

    def test_cluster_marker_de_is_explicitly_descriptive_and_circular(self):
        result = {
            "top_markers": [{"gene": "X", "pvals_adj": 0.001}],
            "n_significant": 1,
        }
        governed = apply_inference_state("differential_expression", result, {})
        self.assertEqual(governed["analysis_scope"], "descriptive_marker_discovery")
        self.assertFalse(governed["inferentially_licensed"])
        self.assertIn("circular_inference_risk", governed["validity_flags"])
        self.assertIn("cell_unit_not_inferential", governed["validity_flags"])
        self.assertEqual(
            governed["inference_state"]["allowed_interpretation_level"],
            InterpretationLevel.DESCRIPTIVE_ONLY.value,
        )
        self.assertIsNone(governed["inference_state"]["conclusion"])

    def test_two_by_two_is_low_power_even_with_significant_genes(self):
        result = {
            "n_significant_fdr_0_05": 380,
            "n_samples": 4,
            "samples_per_age": {"3m": 2, "24m": 2},
            "results": [{"gene": "X", "padj": 0.01}],
        }
        self.assertEqual(
            assign_inference_state("run_deseq2", result),
            InferenceState.LOW_POWER,
        )

    def test_four_by_four_can_be_inferential(self):
        result = {
            "n_significant_fdr_0_05": 10,
            "n_samples": 8,
            "samples_per_age": {"3m": 4, "24m": 4},
            "results": [{"gene": "X", "padj": 0.01}],
        }
        self.assertEqual(
            assign_inference_state("run_deseq2", result),
            InferenceState.SIGNIFICANT_INFERENTIAL,
        )

    def test_no_significant_genes_is_not_significant(self):
        result = {
            "n_significant_fdr_0_05": 0,
            "n_samples": 4,
            "samples_per_age": {"3m": 2, "24m": 2},
            "results": [{"gene": "X", "padj": 0.9}],
        }
        self.assertEqual(
            assign_inference_state("run_deseq2", result),
            InferenceState.NOT_SIGNIFICANT,
        )

    def test_suspect_plausibility_downgrades_to_descriptive(self):
        # Well-powered (4v4) and significant, but the plausibility gate flagged the
        # effect sizes as a technical artifact -> must NOT be SIGNIFICANT_INFERENTIAL.
        result = {
            "n_significant_fdr_0_05": 814,
            "n_samples": 8,
            "samples_per_age": {"3m": 4, "24m": 4},
            "results": [{"gene": "X", "padj": 0.01, "log2FoldChange": -12.0}],
            "result_plausibility": {"verdict": "suspect", "reasons": ["implausible LFC"]},
        }
        self.assertEqual(
            assign_inference_state("run_deseq2", result),
            InferenceState.DESCRIPTIVE_ONLY,
        )

    def test_suspect_plausibility_sets_validity_flag_and_blocks_conclusion(self):
        result = {
            "n_significant_fdr_0_05": 814,
            "n_samples": 8,
            "samples_per_age": {"3m": 4, "24m": 4},
            "results": [{"gene": "X", "padj": 0.01, "log2FoldChange": -12.0}],
            "result_plausibility": {"verdict": "suspect", "reasons": ["implausible LFC"]},
        }
        record = build_state_record("run_deseq2", result)
        self.assertIn("technical_artifact_risk", record["validity_flags"])
        self.assertFalse(record["validity_gate_passed"])
        self.assertIsNone(record["conclusion"])
        self.assertEqual(
            record["allowed_interpretation_level"],
            InterpretationLevel.DESCRIPTIVE_ONLY.value,
        )

    def test_plausible_result_stays_inferential(self):
        # Same design, but plausibility verdict is ok -> conclusion licensed.
        result = {
            "n_significant_fdr_0_05": 30,
            "n_samples": 8,
            "samples_per_age": {"3m": 4, "24m": 4},
            "results": [{"gene": "X", "padj": 0.01, "log2FoldChange": 1.5}],
            "result_plausibility": {"verdict": "ok", "reasons": []},
        }
        self.assertEqual(
            assign_inference_state("run_deseq2", result),
            InferenceState.SIGNIFICANT_INFERENTIAL,
        )
        record = build_state_record("run_deseq2", result)
        self.assertNotIn("technical_artifact_risk", record["validity_flags"])
        self.assertTrue(record["validity_gate_passed"])

    def test_admissibility_warning_triggers_low_power(self):
        result = {
            "n_significant_fdr_0_05": 5,
            "n_samples": 8,
            "samples_per_age": {"3m": 4, "24m": 4},
            "admissibility_warnings": ["few_replicates: groups ['24m'] have < 3 replicates"],
            "results": [{"gene": "X", "padj": 0.01}],
        }
        low, reasons = _deseq2_low_power(result)
        self.assertTrue(low)
        self.assertIn("few_replicates_per_group", reasons)


if __name__ == "__main__":
    unittest.main()
