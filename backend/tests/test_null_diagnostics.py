"""Paper diagnostic aggregation for constructed-null runs."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "ablation", "agent_null_harness"))

from agent_null_sweep import aggregate_diagnostics


class TestNullDiagnostics(unittest.TestCase):
    def test_aggregates_overlap_prevalence_and_correlations(self):
        rows = []
        for perm, genes, discoveries, ratio in (
            (0, ["A", "B"], 2, (100, 200)),
            (1, ["B", "C"], 2, (100, 300)),
            (2, ["B", "D"], 2, (100, 400)),
        ):
            rows.append({
                "perm": perm,
                "ran_deseq2": True,
                "n_sig": discoveries,
                "meta": {
                    "balance": {"sex": {"F": {"fake_young": 1, "fake_old": perm}}},
                    "fake_young_mice": (["a", "c"] if perm == 0 else ["a", "d"] if perm == 1 else ["b", "c"]),
                    "fake_old_mice": (["b", "d"] if perm == 0 else ["b", "c"] if perm == 1 else ["a", "d"]),
                    "excluded_mice": [f"m{perm}"],
                },
                "evaluation_diagnostics": {
                    "significant_genes": genes,
                    "significant_gene_prevalence": [{"gene": gene, "n_donors_expressed": 1} for gene in genes],
                    "donor_pseudobulk": [
                        {"sample_id": "a", "group": "fake_A", "library_size": ratio[0], "n_cells": 20, "pca_distance": 1.0},
                        {"sample_id": "b", "group": "fake_B", "library_size": ratio[1], "n_cells": 20, "pca_distance": 2.0},
                    ],
                },
            })
        result = aggregate_diagnostics(rows)
        self.assertEqual(result["n_runs_with_diagnostics"], 3)
        self.assertEqual(result["gene_recurrence_top100"][0]["gene"], "B")
        self.assertEqual(result["gene_recurrence_top100"][0]["runs"], 3)
        self.assertAlmostEqual(result["gene_overlap"]["matrix"][0][1], 1 / 3, places=4)
        self.assertEqual(result["donor_prevalence"]["expressed_in_at_most_1_donor"], 6)
        self.assertEqual(len(result["influential_donor_profiles_top50"]), 6)
        sensitivity = result["donor_sensitivity"]
        self.assertIn("2-vs-3", sensitivity["method"])
        self.assertEqual(len(sensitivity["donor_exclusion_effects"]), 7)
        self.assertGreater(len(sensitivity["nearest_valid_partition_pairs"]), 0)


if __name__ == "__main__":
    unittest.main()
