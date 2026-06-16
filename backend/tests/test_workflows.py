"""Workflow graph definitions."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.workflows import WORKFLOWS


class TestWorkflows(unittest.TestCase):
    def test_panel_step_order(self):
        tools = [s.tool for s in WORKFLOWS["panel"].steps]
        self.assertEqual(
            tools,
            [
                "find_senescence_markers",
                "senescence_score",
                "generate_umap",
                "get_cluster_annotations",
                "compare_across_age",
            ],
        )

    def test_panel_has_summary(self):
        self.assertTrue(WORKFLOWS["panel"].add_panel_summary)

    def test_deseq2_single_step(self):
        self.assertEqual(len(WORKFLOWS["deseq2"].steps), 1)
        self.assertEqual(WORKFLOWS["deseq2"].steps[0].tool, "run_deseq2")


if __name__ == "__main__":
    unittest.main()
