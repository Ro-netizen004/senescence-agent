import importlib.util
import json
from argparse import Namespace
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "eval" / "external_validation" / "onek1k" / "semisynthetic_benchmark.py"
SPEC = importlib.util.spec_from_file_location("onek1k_semisynthetic", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def synthetic_input(n_donors=24, n_genes=180):
    rng = np.random.default_rng(17)
    donors = [f"donor_{i:03d}" for i in range(n_donors)]
    genes = [f"gene_{i:03d}" for i in range(n_genes)]
    counts = pd.DataFrame(
        rng.poisson(np.linspace(20, 300, n_genes), size=(n_donors, n_genes)),
        index=donors,
        columns=genes,
    )
    metadata = pd.DataFrame(
        {
            "pool": np.repeat(["pool_1", "pool_2"], n_donors // 2),
            "sex": np.tile(["female", "male"], n_donors // 2),
            "age": np.tile(np.arange(n_donors // 2), 2),
        },
        index=pd.Index(donors, name="individual"),
    )
    return counts, metadata


def test_registered_positive_is_reproducible_balanced_and_integer():
    counts, metadata = synthetic_input()
    first = MODULE.scenario_b_positive(counts, metadata, seed=4000, n_genes_per_tier=10)
    second = MODULE.scenario_b_positive(counts, metadata, seed=4000, n_genes_per_tier=10)
    injected, design, truth, allocation = first

    assert truth == second[2]
    assert len(truth) == 30
    assert len(set(truth)) == 30
    assert abs(allocation["direction_counts"]["up_in_B"] - allocation["direction_counts"]["down_in_B"]) <= 3
    assert np.issubdtype(injected.to_numpy().dtype, np.integer)
    assert (injected.to_numpy() >= 0).all()
    group_a = design.index[design["null_group"] == "inject_A"]
    pd.testing.assert_frame_equal(injected.loc[group_a], counts.loc[group_a])


def test_production_gate_allows_paired_design_and_blocks_pool_confounding():
    counts, metadata = synthetic_input()
    _, paired, _, paired_allocation = MODULE.scenario_a_null(counts, metadata, seed=4000)
    paired_gate = MODULE.run_production_admissibility(paired, paired_allocation["groups"])
    assert paired_gate["admissible"] is True

    _, confounded, _, confounded_allocation = MODULE.scenario_c_confounded(
        counts, metadata, seed=4000
    )
    confounded_gate = MODULE.run_production_admissibility(
        confounded, confounded_allocation["groups"]
    )
    assert confounded_gate["admissible"] is False
    assert "pool" in json.dumps(confounded_gate).lower()


def test_checkpoint_requires_exact_protocol_identity(tmp_path):
    args = Namespace(
        h5ad=Path("OneK1K_updated_14_celltypes_980_donors.h5ad"),
        cell_label="Mono C",
        min_cells_per_donor=20,
        n_genes_per_tier=25,
    )
    config_id = MODULE.protocol_id(MODULE.protocol_config(args))
    checkpoint = tmp_path / "allocation_seed4000.json"
    checkpoint.write_text(
        json.dumps(
            {
                "status": "complete_no_llm_calls",
                "scenario": "B",
                "seed": 4000,
                "protocol_id": config_id,
            }
        ),
        encoding="utf-8",
    )
    assert MODULE._valid_checkpoint(checkpoint, "B", 4000, config_id)
    assert not MODULE._valid_checkpoint(checkpoint, "B", 4000, "stale-protocol")
