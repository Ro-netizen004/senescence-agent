"""Intent router → workflow selection (no Gemini, no tools)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.intent_router import (
    _is_bare_pvalue_request,
    _wants_cluster_annotations,
    _wants_explicit_senescence_test,
    _wants_umap,
    route,
)
from agent.workflows import WORKFLOWS


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


class TestIntentRouter(unittest.TestCase):
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

    def test_route_panel(self):
        d = route("Run everything and tell me what's interesting", FAKE)
        self.assertEqual(d.workflow_id, "panel")
        self.assertIn("panel", WORKFLOWS)

    def test_route_coverage(self):
        d = route("What is SenMayo coverage in this dataset?", FAKE)
        self.assertEqual(d.workflow_id, "coverage")

    def test_route_deseq2(self):
        d = route("Run DESeq2 on mesangial cells comparing 24m vs 3m.", FAKE)
        self.assertEqual(d.workflow_id, "deseq2")
        self.assertEqual(d.tool_args["run_deseq2"]["cell_type"], "mesangial cell")
        self.assertEqual(d.tool_args["run_deseq2"]["reference_age"], "3m")
        self.assertEqual(d.tool_args["run_deseq2"]["comparison_age"], "24m")

    def test_route_score_and_annotate(self):
        d = route("Score cells for senescence and show which cluster is highest.", FAKE)
        self.assertEqual(d.workflow_id, "score_and_annotate")

    def test_route_concept(self):
        d = route("what is senmayo score", FAKE)
        self.assertIsNone(d.workflow_id)
        self.assertIn("SenMayo", d.concept_reply or "")


if __name__ == "__main__":
    unittest.main()
