# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad
- Cell type: B cell
- Arm: **governed**
- Null mode: random
- Design: one_sample_per_group
- Prompt style: ordinary
- Prompt: `Which genes differ between fake_A and fake_B in B cell?`
- Permutations completed: 1 / 1

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 0 |
| Blocked | 1 |
| Routing miss | 0 |
| Duplicate allocations skipped | 0 |
| Mean null discoveries (FDR<0.05) | None |
| Raw discovery rate (95% CI) | None None |
| Licensed-claim rate (95% CI) | None None |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Plausibility-withheld rate (95% CI) | None None |
| Exploratory null-discovery rate (95% CI) | None None |
| Inference states | {'BLOCKED': 1} |

Whole donors were assigned to constructed groups independently of the expression matrix, conditional on the selected allocation scheme. Genuine donor heterogeneity may remain, so significant genes are termed null discoveries.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.

## Diagnostics

- Null discoveries: {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}
- Pairwise significant-gene Jaccard: {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}
- Significant-gene donor prevalence: {'distribution': {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}, 'n_gene_run_results': 0, 'expressed_in_at_most_1_donor': 0, 'expressed_in_at_most_2_donors': 0}
- Pseudobulk library sizes: {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}
- Cells per donor: {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}
- Discovery/library-ratio correlation: None
- Discovery/balance correlation: None

Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.