# Many-donor UMI External Validation Protocol

## Status

**Prepared, not executed.** No OneK1K data are currently present in the
repository. Dataset acquisition and schema verification must happen before
freezing seeds or initiating agent/API calls.

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

- **A, schema audit:** donor count, cells per donor, count source, cell types,
  metadata missingness, and candidate stratification variables. No LLM calls.
- **B, statistical smoke test:** one donor-split pseudobulk DESeq2 allocation,
  without either agent.
- **C, paired smoke test:** one governed and one ungoverned call on the same
  frozen result.
- **D, pilot:** 10 unique pairs with a hard API budget.
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
