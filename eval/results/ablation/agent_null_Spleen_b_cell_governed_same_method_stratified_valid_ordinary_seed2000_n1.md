# Agent Null Sweep

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad
- Cell type: B cell
- Arm: **governed_same_method**
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
| Mean null discoveries (FDR<0.05) | 43.0 |
| Raw discovery rate (95% CI) | 1.0 [0.2065, 1.0] |
| Licensed-claim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Reply-overclaim rate (95% CI) | 0.0 [0.0, 0.7935] |
| Any-withheld rate (95% CI) | 1.0 [0.2065, 1.0] |
| Plausibility-withheld rate (95% CI) | 1.0 [0.2065, 1.0] |
| Stability-withheld rate (95% CI) | 1.0 [0.2065, 1.0] |
| Exploratory null-discovery rate (95% CI) | 0.0 [0.0, 0.7935] |
| Inference states | {'DESCRIPTIVE_ONLY': 1} |
| Confounding gate evaluation | {'expected_outcome': 'not_a_confounding_challenge', 'n_evaluable': 1, 'n_unrelated_blocks': 0, 'confusion_matrix': {'true_positive': 0, 'false_negative': 0, 'true_negative': 0, 'false_positive': 0}, 'metric_name': None, 'metric': 1.0, 'metric_ci95': [0.2065, 1.0], 'partial_warning_rate': None, 'partial_warning_rate_ci95': None} |

Whole donors were assigned to constructed groups independently of the expression matrix, conditional on the selected allocation scheme. Genuine donor heterogeneity may remain, so significant genes are termed null discoveries.

## Interpretation

This is an end-to-end test of `run_agent` (routing + gates + DESeq2 + inference state), not the isolated Wilcoxon/t-test null harness.

## Diagnostics

- Null discoveries: {'n': 1, 'mean': 43.0, 'median': 43.0, 'q1': 43.0, 'q3': 43.0, 'min': 43.0, 'max': 43.0}
- Pairwise significant-gene Jaccard: {'n': 0, 'mean': None, 'median': None, 'q1': None, 'q3': None, 'min': None, 'max': None}
- Significant-gene donor prevalence: {'distribution': {'n': 43, 'mean': 8.093, 'median': 8.0, 'q1': 6.0, 'q3': 10.0, 'min': 3.0, 'max': 12.0}, 'n_gene_run_results': 43, 'expressed_in_at_most_1_donor': 0, 'expressed_in_at_most_2_donors': 0}
- Pseudobulk library sizes: {'n': 12, 'mean': 173236843.1667, 'median': 157071405.0, 'q1': 94770381.0, 'q3': 242592721.5, 'min': 32136472.0, 'max': 418292976.0}
- Cells per donor: {'n': 12, 'mean': 216.5, 'median': 242.0, 'q1': 166.5, 'q3': 268.5, 'min': 116.0, 'max': 272.0}
- Discovery/library-ratio correlation: None
- Discovery/balance correlation: None

Full gene recurrence, overlap matrix, donor profiles, and excluded-donor summaries are retained in the JSON output.