# Paper Data Registry

This is the single human-facing index for results being considered for the
paper. Numerical files remain in their experiment packages; this file records
what each result measures, where its evidence lives, and whether it is ready to
cite. Do not cite an artifact marked preliminary as a final result.

## Status key

- **Final candidate:** packaged with protocol and provenance; still requires
  manuscript-level review.
- **Paper-usable pilot:** scientifically sound for its stated scope; caveats
  (e.g., confounded comparison, non-independent allocations) are documented in
  the manuscript and must be preserved.
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

**Status: Paper-usable full-system pilot.** This compares the complete governed
pseudobulk system against an ungoverned per-cell-method ablation. The arms
differ in both governance and statistical method; the result demonstrates the
full-system difference but does not isolate the governance effect. Saved replies
were deterministically rescored with the corrected linter and matched by seed
and donor allocation. The primary derived files are
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
- [x] Add a many-donor UMI statistical-calibration pilot: OneK1K classical
  monocytes, 454 retained donors, 10 fake-label orientations, and 0/10
  allocations with an FDR discovery. This is not an external governance
  endpoint because the shared statistical outputs contained no discoveries.
- [x] Freeze a 156-reply, arm-blinded human-annotation template and prespecified
  rubric for two study-author annotators.
- [ ] Complete both annotations independently, freeze their hashes, calculate
  agreement before adjudication, and package consensus-versus-linter results.
- Verify final artifact checksums and update each protocol before changing status to
  final candidate.

## Package requirements

Each experiment package must retain full numerical results, prompt, dataset
identifier and checksum, arm, method, statistical unit, contrast, covariates,
sample counts, diagnostic states, run date, code revision, and artifact hashes.
PDFs are interface captures; CSV/JSON files are the primary numerical evidence.

## 5. OneK1K external statistical-calibration pilot

**Status: External statistical-calibration candidate.** Ten unique fake-label
allocations each retained 454 classical-monocyte donors (227 per group) from
one 524-donor eligible cohort. Donor-level pseudobulk DESeq2 used the design
`pool + sex + age + null_group`. All 10/10 allocations produced zero discoveries
at FDR < 0.05; 16,067-16,075 genes were tested per allocation.

This result supports calibration in a well-powered many-donor droplet/UMI
setting. It does not estimate an external governance effect, because there were
no discoveries for either arm to communicate or withhold, and the ten label
orientations are not independent cohorts.

Donor reuse is substantial: 449 donors occur in every allocation, the union is
457 donors, and pairwise overlap ranges from 451 to 454 of 454 retained donors.

Evidence: [`onek1k_external_validation/pilot_null_monoc_seed3000_n10/PAPER_RESULTS.md`](onek1k_external_validation/pilot_null_monoc_seed3000_n10/PAPER_RESULTS.md),
[`paper_summary.json`](onek1k_external_validation/pilot_null_monoc_seed3000_n10/paper_summary.json),
and [`per_seed_summary.csv`](onek1k_external_validation/pilot_null_monoc_seed3000_n10/per_seed_summary.csv).

## 6. OneK1K semi-synthetic positive control

**Status: Paper-candidate selectivity validation.** Five many-donor classical-monocyte allocations injected 375 registered donor-level effects. The production firewall admitted and licensed all 5/5 allocations, recovered 358/375 effects (95.47%), preserved 100% direction agreement, and found 11 additional discoveries (pooled empirical FDP 2.98%). All allocations passed donor-stability assessment. This demonstrates that governance can preserve valid signal rather than refusing every analysis. The allocations reuse one donor cohort and are not independent biological cohorts.

Evidence: [`onek1k_external_validation/semisynthetic_positive_monoc_seed4000_n5/PAPER_RESULTS.md`](onek1k_external_validation/semisynthetic_positive_monoc_seed4000_n5/PAPER_RESULTS.md), [`paper_summary.json`](onek1k_external_validation/semisynthetic_positive_monoc_seed4000_n5/paper_summary.json), and [`per_seed_summary.csv`](onek1k_external_validation/semisynthetic_positive_monoc_seed4000_n5/per_seed_summary.csv).

## 7. Confound-gate functional validation

**Status: Paper candidate functional validation.** The production admissibility
gate made 150 decisions across five paired synthetic metadata challenges and 30
unique TMS Spleen B-cell donor allocations. Perfect off-axis confounds were
blocked 30/30; partial confounds were allowed and warned 30/30; balanced
covariates were allowed 30/30; registered aliases were allowed and warned
30/30; and registered aliases plus an off-axis batch were blocked 30/30. There
were no unrelated blocks. No LLM or DESeq2 calls were made.

The same 30 donor allocations are reused across challenges, so this is a
deterministic functional validation rather than 150 independent cohorts.
Evidence: [`confound_gate/PAPER_RESULTS.md`](confound_gate/PAPER_RESULTS.md),
[`confound_gate/paper_summary.json`](confound_gate/paper_summary.json), and
[`confound_gate/design_summary.csv`](confound_gate/design_summary.csv).

## 8. Blinded human validation of reply labels

**Status: In progress; no result is currently paper-usable.** The 156 frozen
replies from the primary same-method experiment were reproducibly shuffled with
seed 42 into two identical blank workbooks. The extraction guard verified 78
governed and 78 ungoverned replies and 156 unique source-arm-allocation records.
Arm, tissue, seed, and allocation metadata are absent from the workbooks.

Two study authors will annotate the replies independently. The public files are
the prespecified [`annotation protocol`](../../ablation/annotation/ANNOTATION_PROTOCOL.md),
blank [`template`](../../ablation/annotation/blinded_annotation_template.xlsx),
and numbered starting workbooks for
[`annotator 1`](../../ablation/annotation/blinded_replies_annotator_1.xlsx) and
[`annotator 2`](../../ablation/annotation/blinded_replies_annotator_2.xlsx).
The arm key remains local and excluded from Git until both annotations are
complete and frozen. Do not cite human agreement, linter accuracy, sensitivity,
or specificity until the finalized annotation package exists.
