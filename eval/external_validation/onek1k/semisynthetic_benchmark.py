"""OneK1K semi-synthetic governance stress test.

Three registered scenarios on OneK1K classical monocytes:

  Scenario A: Clean null (already done in pilot — zero discoveries expected)
  Scenario B: Known positive signal injected at donor-pseudobulk level
  Scenario C: Confounded contrast (group perfectly aligned with pool/batch)

Signal injection happens at the DONOR level, not per-cell, preserving
real donor variability and library-size structure.

Usage:
  python eval/external_validation/onek1k/semisynthetic_benchmark.py \
      --h5ad /path/to/onek1k_monocytes.h5ad \
      --output-dir eval/results/onek1k_semisynthetic \
      --scenarios A B C

Requirements:
  - OneK1K h5ad with classical monocytes, donor IDs, pool, sex, age
  - pydeseq2, scanpy, numpy, pandas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))


def load_pseudobulk(h5ad_path: Path, cell_type: str = "Mono_C"):
    """Load h5ad -> donor-level pseudobulk counts + metadata."""
    import scanpy as sc

    adata = sc.read_h5ad(h5ad_path)
    if "cell_type" in adata.obs.columns:
        adata = adata[adata.obs["cell_type"] == cell_type].copy()

    donor_col = "individual"
    if donor_col not in adata.obs.columns:
        for c in ["donor_id", "sample_id", "donor"]:
            if c in adata.obs.columns:
                donor_col = c
                break

    donors = adata.obs[donor_col].unique()
    print(f"Loaded {len(donors)} donors, {adata.n_obs} cells")

    pb_list = []
    meta_list = []
    for d in donors:
        mask = adata.obs[donor_col] == d
        subset = adata[mask]
        counts = np.asarray(subset.X.sum(axis=0)).flatten()
        pb_list.append(counts)
        row = subset.obs.iloc[0]
        meta_list.append({
            "donor": d,
            "pool": row.get("pool", ""),
            "sex": row.get("sex", ""),
            "age": row.get("age", ""),
            "n_cells": int(mask.sum()),
        })

    pb_df = pd.DataFrame(pb_list, columns=adata.var_names, index=donors)
    meta_df = pd.DataFrame(meta_list).set_index("donor")
    return pb_df, meta_df, adata.var_names.tolist()


def scenario_a_null(pb_df, meta_df, seed=4000):
    """Clean null: random donor assignment, no injected effect."""
    rng = np.random.RandomState(seed)
    donors = meta_df.index.tolist()
    rng.shuffle(donors)
    n = len(donors) // 2
    groups = {d: "fake_A" for d in donors[:n]}
    groups.update({d: "fake_B" for d in donors[n:]})
    meta_df = meta_df.copy()
    meta_df["null_group"] = meta_df.index.map(groups)
    return pb_df, meta_df, None


def scenario_b_positive(pb_df, meta_df, seed=4000, n_genes_per_tier=25):
    """Inject known donor-level signal into registered genes."""
    rng = np.random.RandomState(seed)
    donors = meta_df.index.tolist()
    rng.shuffle(donors)
    n = len(donors) // 2
    group_a = donors[:n]
    group_b = donors[n:]

    groups = {d: "inject_A" for d in group_a}
    groups.update({d: "inject_B" for d in group_b})
    meta_df = meta_df.copy()
    meta_df["null_group"] = meta_df.index.map(groups)

    genes = pb_df.columns.tolist()
    gene_means = pb_df.mean(axis=0)
    expressed = gene_means[gene_means > 0].index.tolist()
    rng.shuffle(expressed)

    tiers = [
        {"log2fc": 0.25, "genes": expressed[:n_genes_per_tier]},
        {"log2fc": 0.50, "genes": expressed[n_genes_per_tier:2*n_genes_per_tier]},
        {"log2fc": 1.00, "genes": expressed[2*n_genes_per_tier:3*n_genes_per_tier]},
    ]

    pb_injected = pb_df.copy()
    truth = {}
    for tier in tiers:
        fc = 2 ** tier["log2fc"]
        for g in tier["genes"]:
            for d in group_b:
                pb_injected.loc[d, g] = pb_injected.loc[d, g] * fc
            truth[g] = {"injected_log2fc": tier["log2fc"], "direction": "up_in_B"}

    return pb_injected, meta_df, truth


def scenario_c_confounded(pb_df, meta_df, seed=4000):
    """Groups perfectly aligned with pool — admissibility gate should block."""
    pools = meta_df["pool"].unique()
    if len(pools) < 2:
        raise ValueError(f"Need >=2 pools for confound scenario, found {len(pools)}")

    pool_a = pools[0]
    pool_b = pools[1]
    donors_a = meta_df[meta_df["pool"] == pool_a].index.tolist()
    donors_b = meta_df[meta_df["pool"] == pool_b].index.tolist()

    groups = {d: "confound_A" for d in donors_a}
    groups.update({d: "confound_B" for d in donors_b})
    meta_df = meta_df.copy()
    meta_df["null_group"] = meta_df.index.map(groups)
    meta_df = meta_df.loc[donors_a + donors_b]
    pb_subset = pb_df.loc[donors_a + donors_b]

    return pb_subset, meta_df, {"confounded_variable": "pool",
                                 "pool_a": str(pool_a), "pool_b": str(pool_b)}


def run_deseq2(pb_df, meta_df, group_col="null_group", covariates=None):
    """Run pyDESeq2 on donor-level pseudobulk."""
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    if covariates is None:
        covariates = [c for c in ["pool", "sex", "age"] if c in meta_df.columns]

    design_factors = covariates + [group_col]
    counts = pb_df.loc[meta_df.index].astype(int)
    groups = sorted(meta_df[group_col].unique())

    dds = DeseqDataSet(
        counts=counts,
        metadata=meta_df[design_factors],
        design_factors=design_factors,
    )
    dds.deseq2()
    stat = DeseqStats(dds, contrast=[group_col, groups[1], groups[0]])
    stat.summary()
    results = stat.results_df.copy()
    n_sig = int((results["padj"] < 0.05).sum())
    return results, n_sig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--h5ad", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scenarios", nargs="+", default=["A", "B", "C"],
                        choices=["A", "B", "C"])
    parser.add_argument("--seed", type=int, default=4000)
    parser.add_argument("--n-allocations", type=int, default=5,
                        help="Number of random allocations per scenario")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pb_df, meta_df, gene_names = load_pseudobulk(args.h5ad)
    print(f"Pseudobulk: {pb_df.shape[0]} donors x {pb_df.shape[1]} genes")

    scenario_fns = {
        "A": scenario_a_null,
        "B": scenario_b_positive,
        "C": scenario_c_confounded,
    }

    for sc_name in args.scenarios:
        print(f"\n{'='*60}")
        print(f"Scenario {sc_name}")
        print(f"{'='*60}")

        sc_dir = args.output_dir / f"scenario_{sc_name}"
        sc_dir.mkdir(parents=True, exist_ok=True)

        for alloc_i in range(args.n_allocations):
            seed = args.seed + alloc_i
            print(f"\n  Allocation {alloc_i+1}/{args.n_allocations} (seed={seed})")

            fn = scenario_fns[sc_name]
            pb_mod, meta_mod, truth = fn(pb_df, meta_df, seed=seed)

            if sc_name == "C":
                print(f"  Confounded on: {truth}")
                record = {
                    "scenario": sc_name,
                    "seed": seed,
                    "truth": truth,
                    "note": "Admissibility gate should REFUSE this contrast",
                    "n_donors": len(meta_mod),
                }
            else:
                try:
                    results, n_sig = run_deseq2(pb_mod, meta_mod, "null_group")
                    print(f"  DESeq2: {n_sig} significant genes (FDR<0.05)")

                    record = {
                        "scenario": sc_name,
                        "seed": seed,
                        "n_donors": len(meta_mod),
                        "n_genes_tested": len(results),
                        "n_significant_fdr_0_05": n_sig,
                        "truth": truth,
                    }

                    if truth and sc_name == "B":
                        injected_genes = set(truth.keys())
                        sig_genes = set(results[results["padj"] < 0.05].index)
                        tp = len(injected_genes & sig_genes)
                        fn_ = len(injected_genes - sig_genes)
                        fp = len(sig_genes - injected_genes)
                        record["sensitivity"] = tp / len(injected_genes) if injected_genes else 0
                        record["empirical_fdr"] = fp / len(sig_genes) if sig_genes else 0
                        record["true_positives"] = tp
                        record["false_negatives"] = fn_
                        record["false_positives"] = fp
                        print(f"  Sensitivity: {record['sensitivity']:.3f}, "
                              f"Empirical FDR: {record['empirical_fdr']:.3f}")

                except Exception as e:
                    print(f"  DESeq2 error: {e}")
                    record = {"scenario": sc_name, "seed": seed, "error": str(e)}

            outfile = sc_dir / f"allocation_seed{seed}.json"
            outfile.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    print(f"\nAll results saved to {args.output_dir}")


if __name__ == "__main__":
    main()
