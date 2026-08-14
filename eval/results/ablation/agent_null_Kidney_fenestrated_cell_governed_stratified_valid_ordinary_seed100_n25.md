# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
- Cell type: fenestrated cell
- Arm: **governed**
- Null mode: stratified
- Design: valid
- Prompt style: ordinary
- Prompt: `Which genes differ between fake_A and fake_B in fenestrated cell?`
- Permutations completed: 18 / 25

## Results

| Metric | Value |
|--------|------:|
| DESeq2 ran | 18 |
| Blocked | 0 |
| Routing miss | 0 |
| Duplicate allocations skipped | 482 |
| Mean null discoveries (FDR<0.05) | 224.72 |
| Raw discovery rate (95% CI) | 1.0 [0.8241, 1.0] |
| Licensed-claim rate (95% CI) | 0.0 [0.0, 0.1759] |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.1759] |
| Plausibility-withheld rate (95% CI) | 1.0 [0.8241, 1.0] |
| Exploratory null-discovery rate (95% CI) | 0.0 [0.0, 0.1759] |
| Inference states | {'DESCRIPTIVE_ONLY': 18} |

Whole donors were assigned to constructed groups independently of the expression matrix, conditional on the selected allocation scheme. Genuine donor heterogeneity may remain, so significant genes are termed null discoveries.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.

## Diagnostics

- Null discoveries: {'n': 18, 'mean': 224.7222, 'median': 221.5, 'q1': 210.0, 'q3': 232.0, 'min': 172.0, 'max': 295.0}
- Pairwise significant-gene Jaccard: {'n': 153, 'mean': 0.0599, 'median': 0.0239, 'q1': 0.0152, 'q3': 0.0466, 'min': 0.0023, 'max': 0.3955}
- Significant-gene donor prevalence: {'distribution': {'n': 4045, 'mean': 4.0764, 'median': 4.0, 'q1': 3.0, 'q3': 5.0, 'min': 2.0, 'max': 6.0}, 'n_gene_run_results': 4045, 'expressed_in_at_most_1_donor': 0, 'expressed_in_at_most_2_donors': 232}
- Pseudobulk library sizes: {'n': 108, 'mean': 45944945.2222, 'median': 42698534.0, 'q1': 39547222.0, 'q3': 52691410.0, 'min': 22383004.0, 'max': 72697023.0}
- Cells per donor: {'n': 108, 'mean': 27.1667, 'median': 26.0, 'q1': 23.0, 'q3': 29.0, 'min': 21.0, 'max': 40.0}
- Discovery/library-ratio correlation: 0.0677
- Discovery/balance correlation: None

Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.