import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "eval" / "external_validation" / "onek1k" / "full_agent_positive.py"
SPEC = importlib.util.spec_from_file_location("onek1k_full_agent_positive", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def fixture_input():
    donors = [f"donor_{i:02d}" for i in range(8)]
    genes = [f"gene_{i:02d}" for i in range(12)]
    counts = pd.DataFrame(
        np.arange(1, len(donors) * len(genes) + 1).reshape(len(donors), len(genes)),
        index=donors,
        columns=genes,
    )
    metadata = pd.DataFrame(
        {
            "pool": np.repeat(["p1", "p2"], 4),
            "sex": np.tile(["female", "male"], 4),
            "age": np.arange(8),
            "null_group": np.tile(["inject_A", "inject_B"], 4),
        },
        index=pd.Index(donors, name="individual"),
    )
    return counts, metadata


def test_agent_fixture_round_trips_registered_pseudobulk_counts():
    from tools.build_pseudobulk import build_pseudobulk_matrix

    counts, metadata = fixture_input()
    data = MODULE.make_agent_adata(counts, metadata)
    rebuilt, rebuilt_meta = build_pseudobulk_matrix(
        data,
        "Mono C",
        sample_column="sample_id",
        group_column="null_group",
        covariates=["pool", "sex"],
    )
    pd.testing.assert_frame_equal(rebuilt, counts, check_dtype=False)
    assert rebuilt_meta.index.tolist() == counts.index.tolist()
    assert data.n_obs == len(counts) * 20
    assert data.obs["cell_type"].unique().tolist() == ["Mono C"]


def test_score_requires_exactly_one_deseq2_call():
    score = MODULE.score_response({"reply": "", "tool_calls": []}, {}, None)
    assert score["routing_success"] is False


def test_statistical_signature_ignores_governance_only_fields():
    shared = {
        "n_significant_fdr_0_05": 2,
        "n_samples": 8,
        "samples_per_group": {"inject_A": 4, "inject_B": 4},
        "group_column": "null_group",
        "reference_group": "inject_A",
        "comparison_group": "inject_B",
        "design_factors": ["pool", "sex", "null_group"],
        "covariates_used": ["pool", "sex"],
        "results": [{"gene": "g1", "log2FoldChange": 1.0, "pvalue": 0.01, "padj": 0.02}],
    }
    governed = dict(shared, inference_state={"state": "SIGNIFICANT_INFERENTIAL"})
    ungoverned = dict(shared, governance_mode="ungoverned_ablation")
    assert MODULE._hash(MODULE._statistical_signature(governed)) == MODULE._hash(
        MODULE._statistical_signature(ungoverned)
    )


def test_positive_communication_score_accepts_renderer_wording():
    response = {
        "reply": "**76 gene(s)** with padj < 0.05 for Mono C.",
        "tool_calls": [
            {
                "name": "run_deseq2",
                "args": {
                    "cell_type": "Mono C",
                    "group_column": "null_group",
                    "reference_group": "inject_A",
                    "comparison_group": "inject_B",
                },
                "result": {
                    "n_significant_fdr_0_05": 76,
                    "results": [],
                    "covariates_used": ["pool", "sex"],
                    "evaluation_diagnostics": {"significant_genes": []},
                },
            }
        ],
    }
    score = MODULE.score_response(response, {}, 76)
    assert score["communicates_significant_result"] is True
