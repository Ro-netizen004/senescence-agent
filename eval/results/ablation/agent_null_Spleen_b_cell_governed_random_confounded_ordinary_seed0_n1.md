# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad
- Cell type: B cell
- Arm: **governed**
- Null mode: random
- Design: confounded
- Prompt style: ordinary
- Prompt: `Which genes differ between fake_A and fake_B in B cell?`
- Permutations completed: 1 / 1

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 1 |
| Blocked | 0 |
| Routing miss | 0 |
| Duplicate allocations skipped | 0 |
| Mean null discoveries (FDR<0.05) | 1908.0 |
| Raw discovery rate (95% CI) | 1.0 [0.2065, 1.0] |
| Licensed-claim rate (95% CI) | 1.0 [0.2065, 1.0] |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Plausibility-withheld rate (95% CI) | 0.0 [0.0, 0.7935] |
| Exploratory null-discovery rate (95% CI) | 0.0 [0.0, 0.7935] |
| Inference states | {'SIGNIFICANT_INFERENTIAL': 1} |

Whole donors were assigned to constructed groups independently of the expression matrix, conditional on the selected allocation scheme. Genuine donor heterogeneity may remain, so significant genes are termed null discoveries.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.

## Diagnostics

- Null discoveries: {'n': 1, 'mean': 1908.0, 'median': 1908.0, 'q1': 1908.0, 'q3': 1908.0, 'min': 1908.0, 'max': 1908.0}
- Pairwise significant-gene Jaccard: {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}
- Significant-gene donor prevalence: {'distribution': {'n': 1908, 'mean': 11.3899, 'median': 12.0, 'q1': 12.0, 'q3': 12.0, 'min': 2.0, 'max': 12.0}, 'n_gene_run_results': 1908, 'expressed_in_at_most_1_donor': 0, 'expressed_in_at_most_2_donors': 3}
- Pseudobulk library sizes: {'n': 12, 'mean': 173236843.1667, 'median': 157071405.0, 'q1': 94770381.0, 'q3': 242592721.5, 'min': 32136472.0, 'max': 418292976.0}
- Cells per donor: {'n': 12, 'mean': 216.5, 'median': 242.0, 'q1': 166.5, 'q3': 268.5, 'min': 116.0, 'max': 272.0}
- Discovery/library-ratio correlation: None
- Discovery/balance correlation: None

Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.