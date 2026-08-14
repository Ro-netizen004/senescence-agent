"""Leave-one-donor-out stability gate for pseudobulk DESeq2 results."""

import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.run_deseq2 import assess_replicate_stability


class TestReplicateStability(unittest.TestCase):
    def _meta(self):
        samples = [f"A{i}" for i in range(4)] + [f"B{i}" for i in range(4)]
        return pd.DataFrame({"group": ["A"] * 4 + ["B"] * 4}, index=samples)

    def _results(self):
        return pd.DataFrame(
            {"padj": [0.01], "log2FoldChange": [2.0]}, index=["signal"]
        )

    def test_consistent_donor_effect_is_stable(self):
        counts = pd.DataFrame({
            "signal": [10, 11, 9, 10, 100, 105, 95, 102],
            "background": [100] * 8,
        }, index=self._meta().index)
        result = assess_replicate_stability(
            counts, self._meta(), self._results(), "group", "A", "B"
        )
        self.assertEqual(result["verdict"], "stable")
        self.assertEqual(result["stable_gene_fraction"], 1.0)

    def test_single_donor_effect_is_unstable(self):
        counts = pd.DataFrame({
            "signal": [10, 10, 10, 10, 10, 10, 10, 1000],
            "background": [100] * 8,
        }, index=self._meta().index)
        result = assess_replicate_stability(
            counts, self._meta(), self._results(), "group", "A", "B"
        )
        self.assertEqual(result["verdict"], "unstable")
        self.assertEqual(result["n_stable_genes"], 0)

    def test_three_per_group_is_insufficient_for_loo_gate(self):
        meta = self._meta().iloc[:3].copy()
        meta = pd.concat([meta, self._meta().iloc[4:7]])
        counts = pd.DataFrame(
            {"signal": [10, 10, 10, 100, 100, 100], "background": [100] * 6},
            index=meta.index,
        )
        result = assess_replicate_stability(
            counts, meta, self._results(), "group", "A", "B"
        )
        self.assertEqual(result["verdict"], "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
