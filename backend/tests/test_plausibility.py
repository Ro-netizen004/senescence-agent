"""Gate 2 result-plausibility check (effect-size / directional-skew artifact flag).

Run:  backend/venv/Scripts/python.exe -m unittest tests.test_plausibility
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.run_deseq2 import assess_de_plausibility  # noqa: E402


class TestPlausibility(unittest.TestCase):
    def test_artifact_extreme_magnitudes_flagged(self):
        # Mimics the aorta case: hundreds of hits with implausible |log2FC|.
        rng = np.random.default_rng(0)
        n = 400
        lfc = -rng.uniform(8, 44, size=n)
        df = pd.DataFrame(
            {"log2FoldChange": lfc, "padj": rng.uniform(1e-5, 0.049, size=n)},
            index=[f"G{i}" for i in range(n)],
        )
        p = assess_de_plausibility(df)
        self.assertEqual(p["verdict"], "suspect")
        self.assertGreater(p["median_abs_log2fc"], 8)
        self.assertTrue(p["reasons"])

    def test_one_directional_flagged(self):
        # Modest magnitudes but ~all one direction -> systematic-difference flag.
        rng = np.random.default_rng(1)
        n = 200
        lfc = rng.uniform(1, 4, size=n)  # all positive
        df = pd.DataFrame(
            {"log2FoldChange": lfc, "padj": rng.uniform(1e-4, 0.049, size=n)},
            index=[f"G{i}" for i in range(n)],
        )
        p = assess_de_plausibility(df)
        self.assertEqual(p["verdict"], "suspect")
        self.assertGreaterEqual(p["pct_up"], 90)

    def test_realistic_result_passes(self):
        # Modest, mixed-direction effect sizes -> plausible.
        rng = np.random.default_rng(2)
        lfc = np.concatenate([rng.normal(1.5, 1.0, 150), -rng.normal(1.5, 1.0, 150)])
        df = pd.DataFrame(
            {"log2FoldChange": lfc, "padj": rng.uniform(1e-4, 0.049, size=len(lfc))},
            index=[f"H{i}" for i in range(len(lfc))],
        )
        p = assess_de_plausibility(df)
        self.assertEqual(p["verdict"], "ok")
        self.assertFalse(p["reasons"])

    def test_few_genes_not_flagged(self):
        # Below the minimum, we don't judge skew/fraction (avoids noise).
        rng = np.random.default_rng(3)
        n = 5
        df = pd.DataFrame(
            {"log2FoldChange": -rng.uniform(9, 20, size=n),
             "padj": rng.uniform(1e-4, 0.049, size=n)},
            index=[f"F{i}" for i in range(n)],
        )
        p = assess_de_plausibility(df)
        self.assertEqual(p["verdict"], "ok")


if __name__ == "__main__":
    unittest.main()
