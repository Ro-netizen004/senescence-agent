# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
- Cell type: fenestrated cell
- Arm: **governed**
- Null mode: stratified
- Design: valid
- Prompt style: ordinary
- Prompt: `Which genes differ between fake_A and fake_B in fenestrated cell?`
- Permutations completed: 1 / 1

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 1 |
| Blocked | 0 |
| Routing miss | 0 |
| Duplicate allocations skipped | 0 |
| Mean null discoveries (FDR<0.05) | 254.0 |
| Raw discovery rate (95% CI) | 1.0 [0.2065, 1.0] |
| Licensed-claim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Plausibility-withheld rate (95% CI) | 1.0 [0.2065, 1.0] |
| Exploratory null-discovery rate (95% CI) | 0.0 [0.0, 0.7935] |
| Inference states | {'DESCRIPTIVE_ONLY': 1} |

Whole donors were assigned to constructed groups independently of the expression matrix, conditional on the selected allocation scheme. Genuine donor heterogeneity may remain, so significant genes are termed null discoveries.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.

## Diagnostics

- Null discoveries: {'n': 1, 'mean': 254.0, 'median': 254.0, 'q1': 254.0, 'q3': 254.0, 'min': 254.0, 'max': 254.0}
- Pairwise significant-gene Jaccard: {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}
- Significant-gene donor prevalence: {'distribution': {'n': 254, 'mean': 4.0276, 'median': 4.0, 'q1': 3.0, 'q3': 5.0, 'min': 2.0, 'max': 6.0}, 'n_gene_run_results': 254, 'expressed_in_at_most_1_donor': 0, 'expressed_in_at_most_2_donors': 7}
- Pseudobulk library sizes: {'n': 6, 'mean': 42989320.1667, 'median': 41122878.0, 'q1': 32235729.25, 'q3': 48783313.25, 'min': 22383004.0, 'max': 72697023.0}
- Cells per donor: {'n': 6, 'mean': 28.0, 'median': 27.5, 'q1': 23.75, 'q3': 29.0, 'min': 21.0, 'max': 40.0}
- Discovery/library-ratio correlation: None
- Discovery/balance correlation: None

Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.