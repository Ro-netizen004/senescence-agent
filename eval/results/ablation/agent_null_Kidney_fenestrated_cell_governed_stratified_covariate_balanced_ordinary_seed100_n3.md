# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
- Cell type: fenestrated cell
- Arm: **governed**
- Null mode: stratified
- Design: covariate_balanced
- Prompt style: ordinary
- Prompt: `Which genes differ between fake_A and fake_B in fenestrated cell?`
- Permutations completed: 3 / 3

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 3 |
| Blocked | 0 |
| Routing miss | 0 |
| Duplicate allocations skipped | 0 |
| Mean null discoveries (FDR<0.05) | 189.0 |
| Raw discovery rate (95% CI) | 1.0 [0.4385, 1.0] |
| Licensed-claim rate (95% CI) | 0.0 [0.0, 0.5615] |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.5615] |
| Plausibility-withheld rate (95% CI) | 1.0 [0.4385, 1.0] |
| Exploratory null-discovery rate (95% CI) | 0.0 [0.0, 0.5615] |
| Inference states | {'DESCRIPTIVE_ONLY': 3} |

Whole donors were assigned to constructed groups independently of the expression matrix, conditional on the selected allocation scheme. Genuine donor heterogeneity may remain, so significant genes are termed null discoveries.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.

## Diagnostics

- Null discoveries: {'n': 3, 'mean': 189.0, 'median': 177.0, 'q1': 174.5, 'q3': 197.5, 'min': 172.0, 'max': 218.0}
- Pairwise significant-gene Jaccard: {'n': 3, 'mean': 0.029, 'median': 0.0265, 'q1': 0.0236, 'q3': 0.0332, 'min': 0.0207, 'max': 0.04}
- Significant-gene donor prevalence: {'distribution': {'n': 567, 'mean': 4.1587, 'median': 4.0, 'q1': 3.0, 'q3': 5.0, 'min': 2.0, 'max': 6.0}, 'n_gene_run_results': 567, 'expressed_in_at_most_1_donor': 0, 'expressed_in_at_most_2_donors': 20}
- Pseudobulk library sizes: {'n': 18, 'mean': 42989320.1667, 'median': 41122878.0, 'q1': 29798565.0, 'q3': 50811573.0, 'min': 22383004.0, 'max': 72697023.0}
- Cells per donor: {'n': 18, 'mean': 28.0, 'median': 27.5, 'q1': 23.0, 'q3': 29.0, 'min': 21.0, 'max': 40.0}
- Discovery/library-ratio correlation: 0.7166
- Discovery/balance correlation: None

Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.