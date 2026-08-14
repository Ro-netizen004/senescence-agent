"""Dashboard-selected DESeq2 covariates flow into governed routing."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anndata as ad
import numpy as np
import pandas as pd

from agent.column_roles import apply_column_overrides, build_column_roles
from agent.intent_router import route


def make_adata():
    rows = []
    for group in ("control", "treated"):
        for i in range(3):
            sample = f"{group}_{i}"
            for _ in range(20):
                rows.append({
                    "sample_id": sample,
                    "condition": group,
                    "cell_type": "B cell",
                    "sex": "female" if i % 2 == 0 else "male",
                    "cell_qc": i,
                })
    obs = pd.DataFrame(rows, index=[f"cell_{i}" for i in range(len(rows))])
    a = ad.AnnData(X=np.ones((len(obs), 2), dtype=int), obs=obs)
    a.layers["counts"] = a.X.copy()
    a.uns["dataset_profile"] = {
        "sample_column": "sample_id",
        "cell_type_column": "cell_type",
        "primary_group_column": "condition",
        "group_columns": [{"column": "condition", "values": ["control", "treated"], "n_levels": 2}],
    }
    return a


class TestColumnRoleCovariates(unittest.TestCase):
    def test_registers_only_exact_donor_level_contrast_alias(self):
        a = make_adata()
        a.obs["condition_copy"] = a.obs["condition"].map({
            "control": "untreated", "treated": "exposed",
        })
        result = apply_column_overrides(a, {
            "contrast_aliases": {"condition": ["condition_copy"]},
        })
        self.assertTrue(result["ok"])
        self.assertEqual(
            a.uns["dataset_profile"]["contrast_aliases"],
            {"condition": ["condition_copy"]},
        )

    def test_rejects_alias_that_is_not_exact_reencoding(self):
        a = make_adata()
        result = apply_column_overrides(a, {
            "contrast_aliases": {"condition": ["sex"]},
        })
        self.assertFalse(result["ok"])
        self.assertIn("not an exact donor-level re-encoding", " ".join(result["errors"]))

    def test_custom_group_records_source_and_mapping(self):
        a = make_adata()
        result = apply_column_overrides(a, {"grouping": {
            "column": "condition",
            "groups": {"baseline": ["control"], "stimulated": ["treated"]},
        }})
        self.assertTrue(result["ok"])
        provenance = a.uns["dataset_profile"]["derived_columns"]["comparison_group"]
        self.assertEqual(provenance["source"], "condition")
        self.assertEqual(provenance["mapping"]["control"], "baseline")

    def test_derived_group_source_is_not_offered_as_covariate(self):
        a = make_adata()
        result = apply_column_overrides(a, {"grouping": {
            "column": "condition",
            "groups": {"baseline": ["control"], "stimulated": ["treated"]},
        }})
        self.assertTrue(result["ok"])
        roles = build_column_roles(a)
        self.assertNotIn("condition", roles["covariate_options"])

    def test_rejects_grouping_source_as_covariate(self):
        a = make_adata()
        result = apply_column_overrides(a, {
            "grouping": {
                "column": "condition",
                "groups": {"baseline": ["control"], "stimulated": ["treated"]},
            },
            "deseq2_covariates": ["condition"],
        })
        self.assertFalse(result["ok"])
        self.assertIn("group-source", " ".join(result["errors"]))

    def test_selector_only_offers_sample_level_columns(self):
        roles = build_column_roles(make_adata())
        self.assertIn("sex", roles["covariate_options"])
        self.assertNotIn("sample_id", roles["covariate_options"])
        self.assertNotIn("condition", roles["covariate_options"])

    def test_saved_covariate_reaches_deterministic_deseq_route(self):
        a = make_adata()
        result = apply_column_overrides(a, {"deseq2_covariates": ["sex"]})
        self.assertTrue(result["ok"])
        decision = route("Run differential expression on B cell between control and treated", a)
        self.assertEqual(decision.tool_args["run_deseq2"]["covariates"], ["sex"])

    def test_rejects_cell_level_covariate(self):
        a = make_adata()
        a.obs["cell_qc"] = np.arange(a.n_obs)
        result = apply_column_overrides(a, {"deseq2_covariates": ["cell_qc"]})
        self.assertFalse(result["ok"])
        self.assertIn("varies within biological samples", " ".join(result["errors"]))


if __name__ == "__main__":
    unittest.main()
