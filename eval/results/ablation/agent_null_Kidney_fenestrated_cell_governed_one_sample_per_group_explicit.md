# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
- Cell type: fenestrated cell
- Arm: **governed**
- Null mode: homogeneous
- Design: one_sample_per_group
- Prompt style: explicit
- Prompt: `Run differential expression on fenestrated cell between 3m and 24m`
- Permutations completed: 1 / 1

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 0 |
| Blocked | 1 |
| Routing miss | 0 |
| Duplicate allocations skipped | 0 |
| Mean FP genes (FDR<0.05) | None |
| Raw discovery rate | None |
| Licensed-claim rate | None |
| Reply-overclaim rate | 0.0 |
| Exploratory FP rate (LOW_POWER, n_sig>0) | None |

Fake labels were assigned independently of expression; no systematic group effect was introduced.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.