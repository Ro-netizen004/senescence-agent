"""Tool-specific replicate thresholds for the admissibility gate."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anndata as ad
import numpy as np
import pandas as pd

from agent.admissibility import check_admissibility


def make_adata(samples_per_group):
    rows = []
    for group in ("3m", "24m"):
        for sample_i in range(samples_per_group):
            sample = f"{group}_{sample_i}"
            for _ in range(20):
                rows.append({
                    "age": group,
                    "sample_id": sample,
                    "cell_ontology_class": "B cell",
                })
    obs = pd.DataFrame(rows, index=[f"cell_{i}" for i in range(len(rows))])
    adata = ad.AnnData(X=np.ones((len(obs), 2)), obs=obs)
    adata.layers["counts"] = adata.X.copy()
    adata.uns["dataset_profile"] = {
        "age_column": "age",
        "primary_group_column": "age",
        "sample_column": "sample_id",
        "cell_type_column": "cell_ontology_class",
    }
    return adata


ARGS = {
    "cell_type": "B cell",
    "reference_age": "3m",
    "comparison_age": "24m",
}


class TestAdmissibilityReplicateThresholds(unittest.TestCase):
    def test_rejects_sample_identifier_as_covariate(self):
        args = dict(ARGS, covariates=["sample_id"])
        result = check_admissibility("run_deseq2", args, make_adata(3))
        self.assertFalse(result["admissible"])
        self.assertTrue(any("invalid_covariates" in r for r in result["blocked_reasons"]))

    def test_deseq2_blocks_two_replicates_per_group(self):
        result = check_admissibility("run_deseq2", ARGS, make_adata(2))
        self.assertFalse(result["admissible"])
        self.assertEqual(result["checks"]["minimum_replicates_per_group"], 3)
        self.assertIn("< 3 biological replicates", " ".join(result["blocked_reasons"]))

    def test_deseq2_allows_three_replicates_per_group(self):
        result = check_admissibility("run_deseq2", ARGS, make_adata(3))
        self.assertTrue(result["admissible"])
        self.assertEqual(result["checks"]["replicates_per_group"], {"3m": 3, "24m": 3})

    def test_score_test_still_allows_two_with_warning(self):
        result = check_admissibility("test_senescence_difference", ARGS, make_adata(2))
        self.assertTrue(result["admissible"])
        self.assertTrue(any("few_replicates" in w for w in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
