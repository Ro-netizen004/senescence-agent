import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import anndata as ad
import numpy as np
import pandas as pd

from tools.percell_inference import differential_expression_percell


class PerCellExportTests(unittest.TestCase):
    def test_exports_every_tested_gene_and_returns_download_url(self):
        adata = ad.AnnData(
            X=np.asarray(
                [
                    [1.0, 0.0, 2.0],
                    [1.2, 0.0, 2.1],
                    [3.0, 1.0, 0.5],
                    [3.2, 1.1, 0.4],
                ]
            ),
            obs=pd.DataFrame(
                {
                    "age": ["3m", "3m", "24m", "24m"],
                    "cell_ontology_class": ["B cell"] * 4,
                    "sample_id": ["m1", "m2", "m3", "m4"],
                },
                index=["c1", "c2", "c3", "c4"],
            ),
            var=pd.DataFrame(index=["g1", "g2", "g3"]),
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("tools.config.OUTPUT_DIR", tmpdir):
                result = differential_expression_percell(adata, "B cell")

            csv_path = Path(tmpdir) / "percell_results.csv"
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8") as handle:
                exported = list(csv.DictReader(handle))

        self.assertEqual(result["download_url"], "/plots/percell_results.csv")
        self.assertEqual(result["governance_mode"], "ungoverned_ablation")
        self.assertEqual(result["method"], "per_cell_wilcoxon")
        self.assertEqual(result["statistical_unit"], "cell")
        self.assertEqual(len(exported), result["n_genes_tested"])
        self.assertEqual(
            {row["gene"] for row in exported},
            {"g1", "g2", "g3"},
        )


if __name__ == "__main__":
    unittest.main()
