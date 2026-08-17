"""The governance ablation must not change the statistical method."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.tool_router import build_tool_map


class _Data:
    uns = {
        "dataset_profile": {
            "age_column": "age",
            "cell_type_column": "cell_type",
            "sample_column": "sample_id",
            "deseq2_covariates": ["sex"],
        }
    }


class TestGovernanceMethodParity(unittest.TestCase):
    def test_deseq2_implementation_and_arguments_match_between_arms(self):
        spec = SimpleNamespace(
            cell_type="B cell",
            sample_column="sample_id",
            group_column="null_group",
            reference_group="fake_A",
            comparison_group="fake_B",
            cell_type_column="cell_type",
        )
        tools = {
            name: (lambda *args, **kwargs: {})
            for name in (
                "generate_umap", "find_senescence_markers", "senescence_score",
                "get_cluster_annotations", "compare_across_age",
                "test_senescence_difference",
            )
        }
        governed_args = {
            "cell_type": "B cell",
            "group_column": "null_group",
            "reference_group": "fake_A",
            "comparison_group": "fake_B",
            "covariates": ["sex"],
        }
        ungoverned_args = {**governed_args, "covariates": []}
        data = _Data()

        with patch.dict(
            "os.environ",
            {"AGENT_EVAL_LOCK_ANALYSIS_SPEC": "on", "AGENT_EVAL_COVARIATES": "sex"},
        ), patch(
            "agent.contrast.resolve_contrast", return_value=spec
        ), patch(
            "agent.tool_router.check_admissibility",
            return_value={"admissible": True, "warnings": []},
        ), patch(
            "agent.tool_router.run_deseq2_wrapper",
            return_value={"method": "pseudobulk_deseq2"},
        ) as wrapper:
            governed = build_tool_map(data, "mouse", tools, governed=True)
            ungoverned = build_tool_map(data, "mouse", tools, governed=False)
            self.assertEqual(
                governed["run_deseq2"](governed_args),
                ungoverned["run_deseq2"](ungoverned_args),
            )

        self.assertEqual(wrapper.call_count, 2)
        self.assertEqual(wrapper.call_args_list[0].args, wrapper.call_args_list[1].args)


if __name__ == "__main__":
    unittest.main()
