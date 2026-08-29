# Many-donor UMI External Validation Protocol

## Status

**Direct statistical smoke complete.** The external dataset remains outside the
repository. Seed 3000 completed without an LLM call: 227 donors per group,
16,071 genes tested, and 0 discoveries at FDR < 0.05.

## Registered pilot input

- File: `OneK1K_updated_14_celltypes_980_donors.h5ad`
- Repository: Zenodo record [18870747](https://zenodo.org/records/18870747)
- Version DOI: `10.5281/zenodo.18870747`
- Concept DOI: `10.5281/zenodo.18870746`
- License: Creative Commons Attribution 4.0 International (CC BY 4.0)
- Accessed: August 2026
- MD5: `a16487819c21506b400cd1d36f09c3e1`
- Shape: 1,266,401 cells x 32,738 genes
- Count source: raw nonnegative integer UMI counts in `X`
- Donor column: `individual` (980 donors total)
- Selected cell type: `cell_label == "Mono C"`
- Eligible population: 38,218 annotated cells; 524 donors have at least 20
  cells, of which 454 are retained by exact pool/sex pairing at seed 3000
- Registered smoke seed: 3000
- Matching variables: exact `pool`/`sex` strata and adjacent donor ages
- DESeq2 design: `pool + sex + null_group`; age is used for matching rather
  than entered as a categorical covariate because OneK1K age is numeric and
  high-cardinality in this wrapper
- Allocation: pair adjacent ages within each pool/sex stratum and randomize the
  orientation of each pair; exclude one optimally chosen donor from odd strata

## Objective

Test whether the governance effect observed in TMS generalizes to a many-donor
droplet/UMI cohort while preserving the biological donor as the statistical
unit.

## Required input contract

- Raw integer UMI counts in `layers["counts"]` or `X`.
- A stable donor identifier with one value per biological individual.
- Cell-type annotations for selecting an abundant, homogeneous lineage.
- Metadata needed for stratification, such as sex, site, batch, ancestry, and
  age where available.
- At least 20 eligible donors after filtering, each with at least 20 selected
  cells.

## Frozen analysis design

1. Select the cell type and donors without inspecting null outcomes.
2. Aggregate raw UMI counts by donor.
3. Assign whole donors, never cells, to fake groups.
4. Stratify on preregistered nuisance variables with adequate overlap.
5. Use the same pseudobulk DESeq2 result table in both arms.
6. Vary only the governance stack.
7. Require parity for allocation ID, significant genes, discovery count,
   design factors, and covariates used or dropped.
8. Use unique orientation-independent allocations and a frozen seed schedule.

## Staged execution

- **A, schema audit (complete):** donor count, cells per donor, count source, cell types,
  metadata missingness, and candidate stratification variables. No LLM calls.
- **B, statistical smoke test (complete):** one donor-split pseudobulk DESeq2
  allocation, without either agent. pyDESeq2 emitted overflow/invalid-value
  optimizer warnings but completed the Wald tests; the saved result had a
  minimum adjusted p-value of 0.9999897 and no FDR discoveries. Future runs
  record warning text and finite/nonfinite counts in `numerical_health`.
- **C, paired smoke test (prepared):** replay the exact frozen result through
  the production governed renderer and one ungoverned LLM narration call.
  This is explicitly a communication-layer smoke, not a routing test.
  The first live attempt failed in the client transport before producing a
  reply or output artifact; the client-lifetime defect was corrected and no
  automatic retry was made.
- **D, statistical pilot (complete):** 10 unique fake-label orientations;
  0/10 had an FDR discovery. Paired narration was stopped after the registered
  seed-3000 smoke because additional zero-discovery narration calls could not
  estimate a governance effect.
- **E, full validation:** expand only after parity, quota, and storage checks.

## Primary endpoint

Difference in reply-overclaim rate between arms under identical DESeq2 output.
Report allocation counts and descriptive intervals and disclose donor reuse.

## Secondary endpoints

- Result-withholding rate.
- Raw null-discovery distribution.
- Donor prevalence and leave-one-donor-out stability.
- Routing, provider, and parity failures.

## Stop conditions

Stop before the next API call on a provider/quota error, parity failure,
missing donor identity, non-integer count source, inadequate donor count, or
an unbalanced off-axis confounder.

## Resumption

`run_pilot.py` stores each seed in its own directory and atomically updates
`pilot_status.json` after every completed stage. On restart it validates and
skips complete `summary.json` and paired artifacts. A failed or partial file is
not accepted as a checkpoint. Run the statistical stage first; paired LLM calls
require a separate explicit `--max-new-api` budget.

## Semi-synthetic selectivity benchmark

`semisynthetic_benchmark.py` is the zero-API, resumable positive-control
benchmark. It uses the validated backed/chunked pseudobulk builder and invokes
the production admissibility, DESeq2, plausibility, donor-stability, and
inference-state functions.

- **Scenario A, clean null:** paired donor allocation with no injected effect;
  the gate should permit analysis and calibrated DE should produce few or no
  discoveries.
- **Scenario B, registered positive:** inject 25 donor-level effects at each
  absolute log2FC tier 0.25, 0.50, and 1.00. Effects are balanced up/down and
  selected reproducibly from genes expressed in at least 90% of donors. The
  endpoint is tier-specific sensitivity, false discoveries, direction
  agreement, and whether governance licenses stable signal.
- **Scenario C, perfect confound:** align the two groups exactly with the two
  largest pools. The production admissibility gate must block before DESeq2.

Each scenario/allocation is written atomically. Resume accepts a checkpoint
only when its seed, scenario, and hash of the analysis-defining protocol match;
`--force` deliberately recomputes it. The source h5ad is never copied into the
repository and no cell-level temporary matrix is written.
