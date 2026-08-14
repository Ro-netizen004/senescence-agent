# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad
- Cell type: B cell
- Arm: **ungoverned**
- Null mode: stratified
- Design: valid
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
| Mean null discoveries (FDR<0.05) | 2906.0 |
| Raw discovery rate (95% CI) | 1.0 [0.2065, 1.0] |
| Licensed-claim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Any-withheld rate (95% CI) | 0.0 [0.0, 0.7935] |
| Plausibility-withheld rate (95% CI) | 0.0 [0.0, 0.7935] |
| Stability-withheld rate (95% CI) | 0.0 [0.0, 0.7935] |
| Exploratory null-discovery rate (95% CI) | 0.0 [0.0, 0.7935] |
| Inference states | {'UNKNOWN': 1} |
| Confounding gate evaluation | {'expected_outcome': 'not_a_confounding_challenge', 'n_evaluable': 1, 'n_unrelated_blocks': 0, 'confusion_matrix': {'true_positive': 0, 'false_negative': 0, 'true_negative': 0, 'false_positive': 0}, 'metric_name': None, 'metric': 1.0, 'metric_ci95': [0.2065, 1.0], 'partial_warning_rate': None, 'partial_warning_rate_ci95': None} |

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