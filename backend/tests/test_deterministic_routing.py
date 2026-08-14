"""Routing heuristics — no Gemini API required."""

import os
import sys
import unittest

import anndata as ad
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.intent_router import (
    route,
    _is_bare_pvalue_request,
    _wants_cluster_annotations,
    _wants_explicit_senescence_test,
    _wants_umap,
)


class _FakeSeries:
    def __init__(self, values):
        self._values = values

    def astype(self, *_args, **_kwargs):
        return self

    def unique(self):
        return self

    def tolist(self):
        return list(self._values)


class _FakeObs:
    def __init__(self, types):
        self._types = types

    def __getitem__(self, key):
        return _FakeSeries(self._types)

    @property
    def columns(self):
        return ["cell_ontology_class"]


class _FakeAdata:
    def __init__(self, cell_types):
        self.obs = _FakeObs(cell_types)


KIDNEY_TYPES = ["T cell", "macrophage", "mesangial cell"]
FAKE = _FakeAdata(KIDNEY_TYPES)


class TestDeterministicRouting(unittest.TestCase):
    def test_umap_prompt(self):
        self.assertTrue(_wants_umap("Generate a UMAP colored by clusters."))
        self.assertFalse(
            _wants_umap("Score cells for senescence and show which cluster is highest.")
        )

    def test_cluster_annotation_prompt(self):
        self.assertTrue(_wants_cluster_annotations("What cell type is each Leiden cluster?"))
        self.assertFalse(_wants_cluster_annotations("Generate a UMAP colored by clusters."))

    def test_bare_pvalue_prompt(self):
        self.assertTrue(_is_bare_pvalue_request("What is the exact p-value?", FAKE))
        self.assertFalse(
            _is_bare_pvalue_request("What is the p-value for aging in T cells?", FAKE)
        )

    def test_explicit_senescence_test_prompt(self):
        self.assertTrue(
            _wants_explicit_senescence_test(
                "Test senescence difference for neurons between 3m and 24m."
            )
        )


    def test_ordinary_named_non_age_groups_override_age_fallback(self):
        obs = pd.DataFrame({
            "cell_ontology_class": ["T cell"] * 4,
            "age": ["3m", "24m", "3m", "24m"],
            "null_group": ["fake_A", "fake_B", "fake_A", "fake_B"],
        }, index=[f"cell_{i}" for i in range(4)])
        adata = ad.AnnData(X=np.ones((4, 2)), obs=obs)
        adata.uns["dataset_profile"] = {
            "cell_type_column": "cell_ontology_class",
            "age_column": "age",
            "primary_group_column": "age",
            "group_columns": [
                {"column": "age", "values": ["3m", "24m"], "n_levels": 2},
                {"column": "null_group", "values": ["fake_A", "fake_B"], "n_levels": 2},
            ],
        }
        decision = route("Which genes differ between fake_A and fake_B in T cell?", adata)
        args = decision.tool_args["run_deseq2"]
        self.assertEqual(args["group_column"], "null_group")
        self.assertEqual(args["reference_group"], "fake_A")
        self.assertEqual(args["comparison_group"], "fake_B")

    def test_named_age_groups_follow_prompt_order_not_profile_order(self):
        obs = pd.DataFrame({
            "cell_ontology_class": ["B cell"] * 4,
            "age": ["3m", "24m", "3m", "24m"],
        }, index=[f"cell_{i}" for i in range(4)])
        adata = ad.AnnData(X=np.ones((4, 2)), obs=obs)
        adata.uns["dataset_profile"] = {
            "cell_type_column": "cell_ontology_class",
            "age_column": "age",
            "primary_group_column": "comparison_group",
            # Deliberately profile-sorted in the opposite order to the prompt.
            "group_columns": [
                {"column": "age", "values": ["24m", "3m"], "n_levels": 2},
                {"column": "comparison_group", "values": ["group_1", "group_2"]},
            ],
            "deseq2_covariates": ["sex"],
        }
        prompt = (
            "Run differential expression on B cell between 3m and 24m "
            "using age as the grouping variable."
        )
        decision = route(prompt, adata)
        args = decision.tool_args["run_deseq2"]
        self.assertEqual(args["group_column"], "age")
        self.assertEqual(args["reference_group"], "3m")
        self.assertEqual(args["comparison_group"], "24m")

if __name__ == "__main__":
    unittest.main()
