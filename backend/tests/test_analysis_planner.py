"""Analysis-plan validation and execution mapping tests (no API calls)."""

import os
import sys
import unittest

import anndata as ad
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.analysis_planner import apply_validated_plan, validate_analysis_plan
from agent.intent_router import RouteDecision


def _adata():
    obs = pd.DataFrame({
        "cell_ontology_class": ["B cell"] * 8,
        "mouse.id": [f"m{i}" for i in range(8)],
        "age": ["3m"] * 4 + ["24m"] * 4,
        "sex": ["female", "male"] * 4,
        "cell_cycle": ["G1", "S"] * 4,
    }, index=[f"c{i}" for i in range(8)])
    data = ad.AnnData(X=np.ones((8, 2)), obs=obs)
    data.uns["dataset_profile"] = {
        "cell_type_column": "cell_ontology_class",
        "sample_column": "mouse.id",
        "age_column": "age",
        "primary_group_column": "age",
        "group_columns": [{"column": "age", "values": ["3m", "24m"]}],
        "deseq2_covariates": ["sex"],
    }
    return data


def _decision():
    return RouteDecision(
        workflow_id="deseq2",
        tool_args={"run_deseq2": {
            "cell_type": "B cell", "group_column": "age",
            "reference_group": "3m", "comparison_group": "24m",
            "covariates": ["sex"],
        }},
    )


def _proposal(**updates):
    value = {
        "method": "pseudobulk_deseq2",
        "cell_type": "B cell",
        "unit_of_replication": "mouse.id",
        "group_column": "age",
        "reference_group": "3m",
        "comparison_group": "24m",
        "covariates": ["sex"],
        "excluded_covariates": {"cell_cycle": "not scientifically justified"},
        "rationale": "Compare donor-level age effects.",
        "expected_limitations": ["Small donor count"],
    }
    value.update(updates)
    return value


class TestAnalysisPlanner(unittest.TestCase):
    def test_valid_plan_is_accepted_and_drives_arguments(self):
        audit = validate_analysis_plan(_proposal(), _adata(), _decision())
        self.assertEqual(audit["status"], "accepted")
        routed = apply_validated_plan(_decision(), audit)
        args = routed.tool_args["run_deseq2"]
        self.assertEqual(args["sample_column"], "mouse.id")
        self.assertEqual(args["covariates"], ["sex"])

    def test_cells_cannot_be_proposed_as_replicates(self):
        audit = validate_analysis_plan(
            _proposal(unit_of_replication="cell_id"), _adata(), _decision()
        )
        self.assertEqual(audit["status"], "corrected_to_deterministic")
        self.assertTrue(any("unit_of_replication" in x for x in audit["corrections"]))

    def test_invalid_group_and_method_are_corrected(self):
        audit = validate_analysis_plan(
            _proposal(method="per_cell_wilcoxon", comparison_group="18m"),
            _adata(), _decision(),
        )
        self.assertEqual(audit["status"], "corrected_to_deterministic")
        self.assertGreaterEqual(len(audit["corrections"]), 2)

    def test_configured_covariate_cannot_be_silently_removed(self):
        audit = validate_analysis_plan(_proposal(covariates=[]), _adata(), _decision())
        self.assertEqual(audit["status"], "corrected_to_deterministic")
        self.assertIn("sex", audit["validated_plan"]["covariates"])

    def test_valid_alternative_contrast_cannot_replace_user_question(self):
        data = _adata()
        data.uns["dataset_profile"]["group_columns"].append(
            {"column": "sex", "values": ["female", "male"]}
        )
        audit = validate_analysis_plan(
            _proposal(
                group_column="sex",
                reference_group="female",
                comparison_group="male",
                covariates=["cell_cycle"],
            ),
            data,
            _decision(),
        )
        self.assertEqual(audit["status"], "corrected_to_deterministic")
        self.assertTrue(any("routed question" in x for x in audit["corrections"]))

    def test_missing_llm_proposal_has_auditable_fallback(self):
        audit = validate_analysis_plan({}, _adata(), _decision())
        self.assertEqual(audit["status"], "deterministic_fallback")
        self.assertEqual(audit["validated_plan"]["unit_of_replication"], "mouse.id")


if __name__ == "__main__":
    unittest.main()
