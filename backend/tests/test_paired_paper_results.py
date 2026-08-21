"""Validation tests for paper-facing paired aggregation."""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "ablation", "agent_null_harness"))

from build_paired_paper_results import _index_permutations, _rescore
from run_paired_ungoverned_shards import _parity_error, _shard_path


class TestPairedPaperResults(unittest.TestCase):
    def test_shard_parity_rejects_statistical_drift(self):
        base = {
            "meta": {"allocation_id": "abc"},
            "n_sig": 2,
            "design_factors": ["sex", "null_group"],
            "covariates_used": ["sex"],
            "covariates_dropped": [],
            "evaluation_diagnostics": {"significant_genes": ["A", "B"]},
        }
        self.assertIsNone(_parity_error(base, dict(base)))
        changed = {**base, "n_sig": 3}
        self.assertEqual(_parity_error(base, changed), "n_sig")

    def test_shard_path_matches_dataset_derived_tissue_slug(self):
        path = _shard_path("Limb_Muscle", "skeletal muscle satellite cell", 2000)
        self.assertIn("agent_null_LimbMuscle_", path.name)

    def _payload(self, rows):
        return {
            "arm": "governed_same_method",
            "mode": "stratified",
            "design": "valid",
            "prompt_style": "ordinary",
            "n_perm_requested": 30,
            "n_perm_completed": len(rows),
            "n_duplicate_allocations_skipped": 600 - len(rows),
            "permutations": rows,
        }

    def test_stale_withholding_field_is_ignored(self):
        row = {
            "n_sig": 43,
            "result_withheld": True,
            "reply": "43 genes met the significance threshold. Top Differentially Expressed Genes",
        }
        overclaim, _, exposed, withheld = _rescore(row)
        self.assertTrue(overclaim)
        self.assertTrue(exposed)
        self.assertFalse(withheld)

    def test_duplicate_seed_is_rejected(self):
        payload = self._payload([{"seed": 2000}, {"seed": 2000}])
        with self.assertRaisesRegex(ValueError, "Duplicate seeds"):
            _index_permutations(
                payload, tissue="Spleen", arm="governed_same_method"
            )

    def test_completion_count_mismatch_is_rejected(self):
        payload = self._payload([{"seed": 2000}])
        payload["n_perm_completed"] = 2
        with self.assertRaisesRegex(ValueError, "Completion-count mismatch"):
            _index_permutations(
                payload, tissue="Spleen", arm="governed_same_method"
            )

    def test_incomplete_allocation_search_is_rejected(self):
        payload = self._payload([{"seed": 2000}])
        payload["n_duplicate_allocations_skipped"] = 0
        with self.assertRaisesRegex(ValueError, "Incomplete allocation search"):
            _index_permutations(
                payload, tissue="Spleen", arm="governed_same_method"
            )

    def test_full_unique_target_may_stop_before_max_attempts(self):
        rows = [{"seed": 2000 + i} for i in range(30)]
        payload = self._payload(rows)
        payload["n_duplicate_allocations_skipped"] = 8
        indexed = _index_permutations(
            payload, tissue="Spleen", arm="governed_same_method"
        )
        self.assertEqual(len(indexed), 30)


if __name__ == "__main__":
    unittest.main()
