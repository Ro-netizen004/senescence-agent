# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
- Cell type: fenestrated cell
- Arm: **governed**
- Null mode: stratified
- Design: confounded_partial
- Prompt style: ordinary
- Prompt: `Which genes differ between fake_A and fake_B in fenestrated cell?`
- Permutations completed: 2 / 2

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 2 |
| Blocked | 0 |
| Routing miss | 0 |
| Duplicate allocations skipped | 0 |
| Mean null discoveries (FDR<0.05) | 231.5 |
| Raw discovery rate (95% CI) | 1.0 [0.3424, 1.0] |
| Licensed-claim rate (95% CI) | 0.0 [0.0, 0.6576] |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.6576] |
| Plausibility-withheld rate (95% CI) | 1.0 [0.3424, 1.0] |
| Exploratory null-discovery rate (95% CI) | 0.0 [0.0, 0.6576] |
| Inference states | {'DESCRIPTIVE_ONLY': 2} |

Whole donors were assigned to constructed groups independently of the expression matrix, conditional on the selected allocation scheme. Genuine donor heterogeneity may remain, so significant genes are termed null discoveries.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.

## Diagnostics

- Null discoveries: {'n': 2, 'mean': 231.5, 'median': 231.5, 'q1': 220.25, 'q3': 242.75, 'min': 209.0, 'max': 254.0}
- Pairwise significant-gene Jaccard: {'n': 1, 'mean': 0.0154, 'median': 0.0154, 'q1': 0.0154, 'q3': 0.0154, 'min': 0.0154, 'max': 0.0154}
- Significant-gene donor prevalence: {'distribution': {'n': 463, 'mean': 4.0389, 'median': 4.0, 'q1': 3.0, 'q3': 5.0, 'min': 2.0, 'max': 6.0}, 'n_gene_run_results': 463, 'expressed_in_at_most_1_donor': 0, 'expressed_in_at_most_2_donors': 21}
- Pseudobulk library sizes: {'n': 12, 'mean': 44897057.25, 'median': 42698534.0, 'q1': 37110057.75, 'q3': 51281532.25, 'min': 22383004.0, 'max': 72697023.0}
- Cells per donor: {'n': 12, 'mean': 26.6667, 'median': 26.0, 'q1': 23.0, 'q3': 29.0, 'min': 21.0, 'max': 40.0}
- Discovery/library-ratio correlation: None
- Discovery/balance correlation: None

Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.