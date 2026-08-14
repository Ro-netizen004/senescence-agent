# TMS Spleen B-cell Positive Control

## Status

**Final candidate - protocol review required before publication.**

This package records a positive-control comparison between the governed agent
and its ungoverned ablation on a real Tabula Muris Senis aging contrast. It
tests whether governance preserves a detectable biological signal. It is not a
gene-level accuracy benchmark because the complete set of truly age-associated
genes is unknown.

## Dataset and contrast

- Dataset: `tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad`
- Dataset SHA-256: `ea3ebbb6d68e9c69238eb276eb0f3454fa404e2505bd18daea5d6dac7a69f309`
- Cell type: B cell
- Contrast: 24m (comparison) versus 3m (reference)
- Grouping column: `age`
- Species: mouse

## Arms

### Governed

- Method: pseudobulk DESeq2
- Statistical unit: biological sample (`sample_id`)
- Samples: 10 (24m: 4; 3m: 6)
- Covariate used: `sex`
- Executed design: `sex + age`
- Inference state: `SIGNIFICANT_INFERENTIAL`
- Significant genes: 2,246
- Donor-stable significant genes: 1,995 (88.82%)
- Plausibility verdict: `ok`

The prompt did not explicitly contain "adjusting for sex"; sex was selected in
the dashboard and is confirmed in the executed-analysis audit and design.

### Ungoverned ablation

- Method: per-cell Wilcoxon/Mann-Whitney test
- Statistical unit: cell
- Cells: 2,056 (24m: 808; 3m: 1,248)
- Covariates used: none
- Genes tested: 5,514
- Significant genes: 2,951 (53.52%)
- Plausibility and donor stability: not assessed

The ungoverned prompt requested adjustment for sex, but the executed per-cell
method did not use covariates. This is an observed difference between the
ablation and governed execution, not a missing value to impute.

## Matched-gene comparison

- Genes present in both result tables: 5,514
- Governed significant genes among the shared genes: 1,472 (26.70%)
- Significant in both arms: 1,167
- Ungoverned significant genes also significant in governed: 39.55%
- Governed shared-universe significant genes also significant in ungoverned: 79.28%
- Effect-direction agreement among jointly significant genes: 100%
- Spearman correlation of log2 fold changes across shared genes: 0.8861
- Spearman correlation among jointly significant genes: 0.8016
- Top-100 overlap: 11 genes
- Ribosomal genes among the top 100: governed 1; ungoverned 31

Do not describe ungoverned-only genes as proven false positives. The appropriate
terms are `ungoverned-only discoveries` or `method-dependent discoveries`.

## Artifact roles

- CSV files are the primary numerical results.
- PDF files are captured website/interface outputs, not formal analysis reports.
- `comparison_summary.json` contains derived comparison statistics.
- `protocol.json` records execution and environment provenance.
- `SHA256SUMS.txt` provides artifact integrity hashes.

## Reproducibility limitation

The repository base commit at packaging time was
`4dde3b41c0cc84ecac1ff11138c710f059c8eeb7`, but the working tree contained
uncommitted agent-development changes. The package is therefore a final
candidate, not yet a frozen publication artifact. Before publication, commit or
tag the finalized code and update `protocol.json` with that immutable revision.

