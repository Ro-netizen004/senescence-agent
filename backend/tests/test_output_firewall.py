"""The renderer must not expose plausibility-failed DE results."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.inference_state import apply_inference_state
from agent.output_renderer import render_strict_output
from agent.output_schema import build_output_schema


class TestOutputFirewall(unittest.TestCase):
    def test_unstable_deseq2_withholds_gene_rows_and_download(self):
        result = {
            "results": [{"gene": "DonorDriven", "log2FoldChange": 2.0, "padj": 0.001}],
            "n_significant_fdr_0_05": 1,
            "n_samples": 8,
            "samples_per_age": {"A": 4, "B": 4},
            "youngest_group": "A", "oldest_group": "B",
            "download_url": "/plots/deseq2_results.csv",
            "result_plausibility": {"verdict": "ok", "reasons": []},
            "replicate_stability": {
                "verdict": "unstable", "n_stable_genes": 0,
                "n_significant_genes": 1,
            },
        }
        governed = apply_inference_state("run_deseq2", result, {"cell_type": "B cell"})
        schema = build_output_schema("run_deseq2", governed, {"cell_type": "B cell"})
        rendered = render_strict_output(schema)
        self.assertTrue(schema["result_withheld"])
        self.assertEqual(schema["metrics"]["top_genes"], [])
        self.assertIsNone(schema["download_url"])
        self.assertIn("donor stability", rendered.lower())
        self.assertNotIn("DonorDriven", rendered)

    def test_suspect_deseq2_withholds_gene_rows_and_download(self):
        result = {
            "results": [{"gene": "FalseHit", "log2FoldChange": 12.0, "padj": 0.001}],
            "n_significant_fdr_0_05": 49,
            "n_samples": 12,
            "samples_per_age": {"3m": 6, "24m": 6},
            "youngest_group": "3m",
            "oldest_group": "24m",
            "download_url": "/plots/deseq2_results.csv",
            "result_plausibility": {
                "verdict": "suspect",
                "reasons": ["implausible effect sizes"],
            },
        }
        governed = apply_inference_state("run_deseq2", result, {"cell_type": "B cell"})
        schema = build_output_schema("run_deseq2", governed, {"cell_type": "B cell"})
        rendered = render_strict_output(schema)

        self.assertTrue(schema["result_withheld"])
        self.assertEqual(schema["metrics"]["top_genes"], [])
        self.assertIsNone(schema["download_url"])
        self.assertIn("Gene-level results were withheld", rendered)
        self.assertNotIn("FalseHit", rendered)
        self.assertNotIn("padj", rendered.lower())
        self.assertNotIn("Download", rendered)


if __name__ == "__main__":
    unittest.main()
