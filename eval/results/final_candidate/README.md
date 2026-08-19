# Paper Data Registry

This is the single human-facing index for results being considered for the
paper. Numerical files remain in their experiment packages; this file records
what each result measures, where its evidence lives, and whether it is ready to
cite. Do not cite an artifact marked preliminary as a final result.

## Status key

- **Final candidate:** packaged with protocol and provenance; still requires
  manuscript-level review.
- **Preliminary:** scientifically useful, but must be rerun or reconciled under
  one frozen revision before publication.
- **Historical:** retained for audit only and not eligible for paper claims.

## 1. Current paper result: same-method governance ablation

**Status: Current paper result.** This is the primary governance-isolation
experiment. Both arms use identical donor-level pseudobulk DESeq2 output and
differ only in the governance stack. Across 78 matched allocations, governed
reply overclaim was 0/78, compared with 72/78 ungoverned; governed results were
withheld in 78/78 allocations, compared with 4/78 ungoverned.

Evidence: [`null_sweep_same_method/PAPER_RESULTS.md`](null_sweep_same_method/PAPER_RESULTS.md),
[`null_sweep_same_method/MANUSCRIPT_RESULTS.md`](null_sweep_same_method/MANUSCRIPT_RESULTS.md),
[`null_sweep_same_method/paired_allocations.csv`](null_sweep_same_method/paired_allocations.csv),
and [`null_sweep_same_method/paper_summary.json`](null_sweep_same_method/paper_summary.json).

## 2. Historical positive control: preservation of a real aging signal

**Status: Historical; rerun required under the current frozen revision.** This
tests whether governance preserves power on a real biological contrast, but its
arms used different statistical methods and it predates the final same-method
null implementation. It must not be presented as the matched positive control
for the current paper result.

| Endpoint | Governed | Ungoverned ablation |
|---|---:|---:|
| Dataset / cell type | TMS Spleen / B cell | TMS Spleen / B cell |
| Contrast | 24m vs 3m | 24m vs 3m |
| Statistical unit | 10 biological samples (4 vs 6) | 2,056 cells (808 vs 1,248) |
| Method | Pseudobulk DESeq2 | Per-cell Wilcoxon |
| Covariates actually used | sex | none |
| Significant genes (FDR < 0.05) | 2,246 | 2,951 |
| Significant genes in shared 5,514-gene universe | 1,472 | 2,951 |
| Donor-stable governed discoveries | 1,995 / 2,246 (88.82%) | not assessed |

Matched comparison: 1,167 genes were significant in both arms; effect direction
agreed for 100% of those genes; all-gene Spearman correlation was 0.8861; top-100
overlap was 11 genes. Ribosomal genes represented 1/100 governed versus 31/100
ungoverned top-ranked genes. Ungoverned-only discoveries are method-dependent
discoveries, not proven false positives.

Evidence and exact provenance: [`positive_control/README.md`](positive_control/README.md),
[`positive_control/comparison_summary.json`](positive_control/comparison_summary.json),
and the governed/ungoverned CSV files in that package. Evaluated agent revision:
`374ae5f26ab1fecfc6b05579bcc818052afa2388`.

## 3. Historical paired null smoke test

**Status: Historical smoke test, not the full null experiment.** Both arms
used the same TMS Spleen B-cell allocation at seed 2000.

| Endpoint | Governed | Ungoverned ablation |
|---|---:|---:|
| Null discoveries | 43 | 2,906 |
| Inference state | `DESCRIPTIVE_ONLY` | not governed (`UNKNOWN` in harness) |
| Licensed inferential claim | no | not applicable |
| Result withheld by governance | yes | no |

This single pair demonstrates the intended mechanism but cannot estimate a
rate. Evidence, checksums, and revision metadata are in
[`null_sweep/README.md`](null_sweep/README.md),
[`null_sweep/raw_results_manifest.csv`](null_sweep/raw_results_manifest.csv),
and [`null_sweep/protocol.json`](null_sweep/protocol.json).

## 4. Historical mixed-method multi-tissue TMS null pilot

**Status: Historical full-system pilot after the same-method redesign.** Saved replies were
deterministically rescored with the corrected linter and matched by seed and
donor allocation. The primary derived files are
[`null_sweep/PAPER_RESULTS.md`](null_sweep/PAPER_RESULTS.md),
[`null_sweep/paired_allocations.csv`](null_sweep/paired_allocations.csv), and
[`null_sweep/paper_summary.json`](null_sweep/paper_summary.json).

| Tissue / cell type | Unique allocations | Mean null discoveries | Raw discovery rate | Licensed-claim rate | Result-withheld rate | State |
|---|---:|---:|---:|---:|---:|---|
| Kidney / epithelial cell of proximal tubule | 6 | 227.67 | 100% | 0% | 100% | 6/6 `DESCRIPTIVE_ONLY` |
| Liver / hepatocyte | 8 | 30.12 | 100% | 0% | 100% | 8/8 `DESCRIPTIVE_ONLY` |
| Spleen / B cell | 30 | 45.87 | 100% | 0% | 100% | 30/30 `DESCRIPTIVE_ONLY` |
| Aorta / aortic endothelial cell | 4 | 164.25 | 100% | 0% | 100% | 4/4 `DESCRIPTIVE_ONLY` |
| Limb muscle / skeletal muscle satellite cell | 30 | 156.40 | 100% | 0% | 100% | 30/30 `DESCRIPTIVE_ONLY` |
| **Pooled** | **78** | **106.82** | **100%** | **0%** | **100%** | **78/78 `DESCRIPTIVE_ONLY`** |

The request was 30 permutations per tissue. Kidney, Liver, and Aorta have only
6, 8, and 4 distinct orientation-independent allocations under the registered
age/sex-stratified design; the harness exhausted those spaces and skipped
duplicates. Mean null discoveries are raw DESeq2 discoveries under donor-split
null labels. They are not automatically false-positive genes because residual
donor heterogeneity remains. The governance endpoint is whether those results
were licensed as inferential claims.

Additional pooled diagnostics: plausibility withholding occurred in 77/78
allocations (98.72%), and stability withholding in 58/78 (74.36%). Raw JSON
artifacts are copied into the ignored local `null_sweep/raw/` archive and
checksummed in [`null_sweep/raw_results_manifest.csv`](null_sweep/raw_results_manifest.csv).

The 78 allocations reuse donors and are not 78 independent biological
experiments. Rates describe the registered allocation set; no biological-
population confidence interval is claimed. The arms also compare the complete
governed pseudobulk system against an ungoverned per-cell-method ablation, so the
difference cannot be attributed to governance gates alone.

The replacement governance-isolation experiment is registered at
[`null_sweep_same_method/`](null_sweep_same_method/README.md). Its arms retain
identical pseudobulk DESeq2 execution and differ only in the governance stack.

## Publication checklist

- [x] Freeze the memory-safe harness at
  `19799611bf7f8e64fed16873d96c7a094e891844`.
- [x] Rerun and deterministically rescore reply-linter outputs.
- [x] Run matched ungoverned allocations for every governed allocation.
- [x] Generate one aggregate CSV/JSON/Markdown set from the paired raw archive.
- [x] Generate the manuscript result and tissue-level figure.
- Add a many-donor UMI dataset such as OneK1K for external generalization.
- Verify final artifact checksums and update each protocol before changing status to
  final candidate.

## Package requirements

Each experiment package must retain full numerical results, prompt, dataset
identifier and checksum, arm, method, statistical unit, contrast, covariates,
sample counts, diagnostic states, run date, code revision, and artifact hashes.
PDFs are interface captures; CSV/JSON files are the primary numerical evidence.
