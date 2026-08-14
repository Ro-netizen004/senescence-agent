"""Regression tests for donor-level confounding detection."""

import os
import sys
import unittest
from types import SimpleNamespace

import pandas as pd
import anndata as ad
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.admissibility import (
    _candidate_covariate_columns,
    _confounded_with,
    _confounding_associations,
    _inconsistent_sample_columns,
    check_admissibility,
)


def dataset(rows):
    return SimpleNamespace(obs=pd.DataFrame(rows), uns={})


class TestConfoundingDetection(unittest.TestCase):
    def _age_adata(self, registered=False, confound_column="development_stage"):
        rows = []
        for age, stage in (("3m", "young"), ("24m", "old")):
            for donor in range(3):
                for _ in range(20):
                    rows.append({
                        "sample_id": f"{age}_{donor}", "age": age,
                        confound_column: stage, "cell_type": "B cell",
                    })
        obs = pd.DataFrame(rows, index=[f"c{i}" for i in range(len(rows))])
        a = ad.AnnData(X=np.ones((len(obs), 2), dtype=int), obs=obs)
        a.layers["counts"] = a.X.copy()
        a.uns["dataset_profile"] = {
            "sample_column": "sample_id", "cell_type_column": "cell_type",
            "primary_group_column": "age",
            "group_columns": [{"column": "age", "values": ["3m", "24m"], "n_levels": 2}],
        }
        if registered:
            a.uns["dataset_profile"]["contrast_aliases"] = {"age": [confound_column]}
        return a

    def test_registered_reencoding_warns_without_blocking(self):
        result = check_admissibility("run_deseq2", {
            "cell_type": "B cell", "group_column": "age",
            "reference_group": "3m", "comparison_group": "24m",
        }, self._age_adata(registered=True))
        self.assertTrue(result["admissible"])
        self.assertEqual(result["checks"]["redundant_contrast_encodings"], ["development_stage"])
        self.assertTrue(any("redundant_contrast_encoding" in w for w in result["warnings"]))

    def test_unregistered_reencoding_still_blocks(self):
        result = check_admissibility("run_deseq2", {
            "cell_type": "B cell", "group_column": "age",
            "reference_group": "3m", "comparison_group": "24m",
        }, self._age_adata())
        self.assertFalse(result["admissible"])
        self.assertEqual(result["checks"]["confounded_with"], ["development_stage"])

    def test_registered_alias_does_not_exempt_off_axis_batch(self):
        a = self._age_adata(registered=True)
        a.obs["batch"] = a.obs["age"].map({"3m": "run1", "24m": "run2"})
        result = check_admissibility("run_deseq2", {
            "cell_type": "B cell", "group_column": "age",
            "reference_group": "3m", "comparison_group": "24m",
        }, a)
        self.assertFalse(result["admissible"])
        self.assertIn("batch", result["checks"]["confounded_with"])

    def test_dashboard_group_derived_from_age_does_not_block_age_contrast(self):
        a = self._age_adata(registered=True)
        a.obs["comparison_group"] = a.obs["age"].map({
            "3m": "group_1", "24m": "group_2",
        })
        a.uns["dataset_profile"]["derived_columns"] = {
            "comparison_group": {
                "source": "age",
                "kind": "value_mapping",
                "mapping": {"3m": "group_1", "24m": "group_2"},
            }
        }
        result = check_admissibility("run_deseq2", {
            "cell_type": "B cell", "group_column": "age",
            "reference_group": "3m", "comparison_group": "24m",
        }, a)
        self.assertTrue(result["admissible"])
        self.assertIn(
            "comparison_group", result["checks"]["redundant_contrast_encodings"]
        )

    def test_dashboard_age_encoding_does_not_exempt_real_batch_confound(self):
        a = self._age_adata(registered=True)
        a.obs["comparison_group"] = a.obs["age"].map({
            "3m": "group_1", "24m": "group_2",
        })
        a.obs["batch"] = a.obs["age"].map({"3m": "run1", "24m": "run2"})
        a.uns["dataset_profile"]["derived_columns"] = {
            "comparison_group": {"source": "age", "kind": "value_mapping"}
        }
        result = check_admissibility("run_deseq2", {
            "cell_type": "B cell", "group_column": "age",
            "reference_group": "3m", "comparison_group": "24m",
        }, a)
        self.assertFalse(result["admissible"])
        self.assertIn("batch", result["checks"]["confounded_with"])

    def test_age_is_scanned_when_null_group_is_the_contrast(self):
        adata = dataset({
            "sample_id": ["s1", "s2", "s3", "s4"],
            "null_group": ["A", "A", "B", "B"],
            "age": ["young", "young", "old", "old"],
        })
        self.assertEqual(
            _confounded_with(adata, "sample_id", "null_group", ["A", "B"]),
            ["age"],
        )

    def test_cell_varying_column_is_not_called_sample_level(self):
        adata = dataset({
            "sample_id": ["s1", "s1", "s2", "s2", "s3", "s3", "s4", "s4"],
            "null_group": ["A", "A", "A", "A", "B", "B", "B", "B"],
            "batch": ["X", "Y", "X", "Y", "Y", "X", "Y", "X"],
        })
        self.assertEqual(
            _inconsistent_sample_columns(adata, "sample_id", ["batch"]),
            {"batch": ["s1", "s2", "s3", "s4"]},
        )
        self.assertNotIn(
            "batch", _candidate_covariate_columns(adata, "sample_id", "null_group")
        )

    def test_missing_other_group_does_not_manufacture_separation(self):
        adata = dataset({
            "sample_id": ["s1", "s2", "s3", "s4"],
            "null_group": ["A", "A", "B", "B"],
            "batch": ["X", "Y", None, None],
        })
        self.assertEqual(
            _confounded_with(adata, "sample_id", "null_group", ["A", "B"]), []
        )

    def test_partial_and_balanced_associations_are_quantified(self):
        partial = dataset({
            "sample_id": [f"s{i}" for i in range(6)],
            "null_group": ["A"] * 3 + ["B"] * 3,
            "batch": ["X", "X", "Y", "Y", "Y", "Y"],
        })
        assessment = _confounding_associations(
            partial, "sample_id", "null_group", ["A", "B"]
        )["batch"]
        self.assertFalse(assessment["perfect_separation"])
        self.assertEqual(assessment["purity"], 0.8333)

        balanced = dataset({
            "sample_id": [f"s{i}" for i in range(8)],
            "null_group": ["A"] * 4 + ["B"] * 4,
            "batch": ["X", "X", "Y", "Y", "X", "X", "Y", "Y"],
        })
        assessment = _confounding_associations(
            balanced, "sample_id", "null_group", ["A", "B"]
        )["batch"]
        self.assertFalse(assessment["perfect_separation"])
        self.assertEqual(assessment["purity"], 0.5)


if __name__ == "__main__":
    unittest.main()
