"""Bounded, JSON-safe dataset preview."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anndata as ad
import numpy as np
import pandas as pd

from tools.dataset_info import build_dataset_preview


class TestDatasetPreview(unittest.TestCase):
    def test_preview_is_bounded_and_json_safe(self):
        obs = pd.DataFrame({
            "sample": ["mouse_1", "mouse_2", "mouse_3"],
            "score": [1.0, np.nan, 3.0],
            "category": pd.Categorical(["A", "B", "A"]),
        }, index=["cell_1", "cell_2", "cell_3"])
        a = ad.AnnData(X=np.ones((3, 3)), obs=obs)
        a.var_names = ["GeneA", "GeneB", "GeneC"]
        preview = build_dataset_preview(a, row_limit=2, gene_limit=2)
        self.assertEqual(len(preview["rows"]), 2)
        self.assertEqual(preview["rows"][0]["cell_id"], "cell_1")
        self.assertIsNone(preview["rows"][1]["score"])
        self.assertEqual(preview["genes"], ["GeneA", "GeneB"])


if __name__ == "__main__":
    unittest.main()
