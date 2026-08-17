"""Validation tests for paper-facing paired aggregation."""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "ablation", "agent_null_harness"))

from build_paired_paper_results import _index_permutations, _rescore


class TestPairedPaperResults(unittest.TestCase):
    def _payload(self, rows):
        return {
            "arm": "governed_same_method",
            "mode": "stratified",
            "design": "valid",
            "prompt_style": "ordinary",
            "n_perm_requested": 30,
            "n_perm_completed": len(rows),
            "n_duplicate_allocations_skipped": 30 - len(rows),
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

    def test_unaccounted_attempts_are_rejected(self):
        payload = self._payload([{"seed": 2000}])
        payload["n_duplicate_allocations_skipped"] = 0
        with self.assertRaisesRegex(ValueError, "Attempt-count mismatch"):
            _index_permutations(
                payload, tissue="Spleen", arm="governed_same_method"
            )


if __name__ == "__main__":
    unittest.main()
