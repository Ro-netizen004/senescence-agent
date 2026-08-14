# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
- Cell type: fenestrated cell
- Arm: **governed**
- Null mode: stratified
- Design: valid
- Prompt style: ordinary
- Prompt: `Which genes differ between 3m and 24m in fenestrated cell?`
- Permutations completed: 3 / 3

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 3 |
| Blocked | 0 |
| Routing miss | 0 |
| Duplicate allocations skipped | 0 |
| Mean FP genes (FDR<0.05) | 205.67 |
| Raw discovery rate | 1.0 |
| Licensed-claim rate | 0.0 |
| Reply-overclaim rate | 0.0 |
| Exploratory FP rate (LOW_POWER, n_sig>0) | 0.0 |

Fake labels were assigned independently of expression; no systematic group effect was introduced.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.