# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad
- Cell type: B cell
- Arm: **governed**
- Null mode: random
- Prompt: `Run differential expression on B cell between 3m and 24m`
- Permutations completed: 5 / 5

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 5 |
| Blocked | 0 |
| Routing miss | 0 |
| Mean FP genes (FDR<0.05) | 46.6 |
| False-discovery rate (inferential) | 0.0 |
| Exploratory FP rate (LOW_POWER, n_sig>0) | 0.0 |

**Truth = 0 DE genes.** Any significant DESeq2 result is a false positive.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.