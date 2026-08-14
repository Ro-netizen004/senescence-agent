"""Stratified donor allocation for the agent null harness."""

import os
import sys
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "ablation", "agent_null_harness"))

from null_builder import (
    FAKE_OLD, FAKE_YOUNG, NULL_GROUP_COLUMN, _canonical_allocation,
    _covariate_audit, _stratified_split, build_null_adata,
)


class TestStratifiedNullBuilder(unittest.TestCase):
    def test_uses_explicit_nonbiological_group_labels(self):
        self.assertEqual(NULL_GROUP_COLUMN, "null_group")
        self.assertEqual({FAKE_YOUNG, FAKE_OLD}, {"fake_A", "fake_B"})

    def test_balances_each_even_stratum_and_uses_all_donors(self):
        mice = [f"m{i}" for i in range(12)]
        strata = {m: (("3m" if i < 6 else "24m"), ("F" if i % 2 else "M")) for i, m in enumerate(mice)}
        a, b, excluded, counts = _stratified_split(mice, strata, np.random.default_rng(0))
        self.assertEqual(len(a), 6)
        self.assertEqual(len(b), 6)
        self.assertEqual(excluded, [])
        self.assertEqual(a | b, set(mice))
        for count in counts.values():
            self.assertLessEqual(abs(count["fake_young"] - count["fake_old"]), 1)

    def test_odd_total_excludes_at_most_one_and_keeps_equal_groups(self):
        mice = [f"m{i}" for i in range(11)]
        strata = {m: ("3m" if i < 5 else "24m", "M" if i < 8 else "F") for i, m in enumerate(mice)}
        a, b, excluded, _ = _stratified_split(mice, strata, np.random.default_rng(2))
        self.assertEqual(len(a), len(b))
        self.assertEqual(len(excluded), 1)
        self.assertEqual((a | b) | set(excluded), set(mice))

    def test_label_reversal_has_same_allocation_id(self):
        a, b = {"m1", "m2"}, {"m3", "m4"}
        self.assertEqual(_canonical_allocation(a, b), _canonical_allocation(b, a))

    def test_confound_audit_uses_one_row_per_donor(self):
        class Data:
            pass
        data = Data()
        data.obs = pd.DataFrame({
            "sample_id": ["s1", "s1", "s2", "s2", "s3", "s3", "s4", "s4"],
            "null_group": ["A", "A", "A", "A", "B", "B", "B", "B"],
            "null_batch": ["X", "X", "X", "X", "Y", "Y", "Y", "Y"],
        })
        audit = _covariate_audit(data, "sample_id", "null_group")
        self.assertEqual(audit["n_samples"], 4)
        self.assertEqual(audit["table"], {"X": {"A": 2}, "Y": {"B": 2}})
        self.assertTrue(audit["perfect_separation"])

    def test_materialized_cell_type_source_is_not_mutated(self):
        import anndata as ad

        samples = [f"m{i}" for i in range(4)]
        obs = pd.DataFrame(
            {
                "cell_ontology_class": ["B cell"] * 80,
                "sample_id": np.repeat(samples, 20),
                "age": np.repeat(["3m", "3m", "24m", "24m"], 20),
            }
        )
        source = ad.AnnData(X=np.ones((80, 2)), obs=obs)
        source.uns["dataset_profile"] = {
            "cell_type_column": "cell_ontology_class",
            "sample_column": "sample_id",
            "age_column": "age",
        }
        source.uns["_null_source_cell_type"] = "B cell"

        tools_module = types.ModuleType("tools")
        pseudobulk_module = types.ModuleType("tools.build_pseudobulk")
        pseudobulk_module._get_sample_column = lambda _adata, suggested: suggested
        with patch.dict(
            sys.modules,
            {"tools": tools_module, "tools.build_pseudobulk": pseudobulk_module},
        ):
            result, _ = build_null_adata(
                None, "B cell", 7, mode="stratified", source_adata=source
            )

        self.assertIn("_null_source_cell_type", source.uns)
        self.assertNotIn(NULL_GROUP_COLUMN, source.obs)
        self.assertNotIn("_null_source_cell_type", result.uns)
        self.assertEqual(set(result.obs[NULL_GROUP_COLUMN]), {FAKE_YOUNG, FAKE_OLD})


if __name__ == "__main__":
    unittest.main()
