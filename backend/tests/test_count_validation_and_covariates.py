"""Raw-count firewall and pseudobulk covariate metadata."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse
from tools.build_pseudobulk import _extract_counts_matrix, build_pseudobulk_matrix, validate_count_matrix
from agent.design_validation import validate_factor_design

class TestCountValidation(unittest.TestCase):
    def test_rejects_group_reused_as_covariate(self):
        meta = pd.DataFrame({"condition": ["A", "A", "B", "B"]})
        with self.assertRaisesRegex(ValueError, "cannot also be an adjustment"):
            validate_factor_design(meta, "condition", ["condition"])

    def test_rejects_missing_sample_covariate_values(self):
        meta = pd.DataFrame({
            "condition": ["A", "A", "B", "B"],
            "batch": ["x", None, "x", "y"],
        })
        with self.assertRaisesRegex(ValueError, "missing sample values"):
            validate_factor_design(meta, "condition", ["batch"])

    def test_rejects_collinear_covariates(self):
        meta = pd.DataFrame({
            "condition": ["A", "A", "B", "B", "A", "B"],
            "batch": ["x", "y", "x", "y", "x", "y"],
            "batch_copy": ["x", "y", "x", "y", "x", "y"],
        })
        with self.assertRaisesRegex(ValueError, "not full rank"):
            validate_factor_design(meta, "condition", ["batch", "batch_copy"])

    def test_full_rank_design_returns_audit(self):
        meta = pd.DataFrame({
            "condition": ["A", "A", "B", "B", "A", "B"],
            "batch": ["x", "y", "x", "y", "x", "y"],
        })
        audit = validate_factor_design(meta, "condition", ["batch"])
        self.assertTrue(audit["full_rank"])
        self.assertEqual(audit["rank"], audit["n_columns"])

    def test_rejects_fractional_normalized_values(self):
        check = validate_count_matrix(sparse.csr_matrix([[0.0, 1.25], [2.0, 0.0]]), "raw.X")
        self.assertFalse(check["valid"])
        self.assertIn("non-integer", check["reason"])

    def test_never_falls_back_to_x(self):
        a = ad.AnnData(X=np.ones((2, 2), dtype=int))
        with self.assertRaisesRegex(ValueError, "neither layers"):
            _extract_counts_matrix(a)

    def test_builds_covariates_and_preserves_counts(self):
        rows = []
        for group in ("A", "B"):
            for donor_i in range(3):
                for _ in range(20):
                    rows.append({"sample_id": f"{group}{donor_i}", "condition": group, "cell_ontology_class": "B cell", "pool": str(donor_i % 2)})
        obs = pd.DataFrame(rows, index=[f"c{i}" for i in range(len(rows))])
        a = ad.AnnData(X=np.zeros((len(obs), 2)), obs=obs)
        a.var_names = ["g1", "g2"]
        a.layers["counts"] = np.ones((len(obs), 2), dtype=int)
        a.uns["dataset_profile"] = {"cell_type_column": "cell_ontology_class", "sample_column": "sample_id"}
        counts, meta = build_pseudobulk_matrix(a, "B cell", group_column="condition", covariates=["pool"])
        self.assertTrue(np.issubdtype(counts.values.dtype, np.integer))
        self.assertEqual(list(meta.columns), ["condition", "pool"])
        self.assertEqual(meta.attrs["count_validation"]["source"], "layers[counts]")

    def test_rejects_covariate_varying_within_sample(self):
        obs = pd.DataFrame({"sample_id": ["s1"] * 20, "condition": ["A"] * 20, "cell_ontology_class": ["B cell"] * 20, "pool": ["x", "y"] * 10})
        a = ad.AnnData(X=np.zeros((20, 1)), obs=obs)
        a.layers["counts"] = np.ones((20, 1), dtype=int)
        a.uns["dataset_profile"] = {"cell_type_column": "cell_ontology_class"}
        with self.assertRaisesRegex(ValueError, "vary within biological samples"):
            build_pseudobulk_matrix(a, "B cell", group_column="condition", covariates=["pool"])

if __name__ == "__main__": unittest.main()
