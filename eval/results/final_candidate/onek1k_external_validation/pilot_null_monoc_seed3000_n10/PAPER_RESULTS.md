# OneK1K Many-donor UMI Null Pilot

**Status: external statistical-calibration candidate; not an agent-governance endpoint.**

Ten unique fake-label allocations each used 454 classical-monocyte donors (227 per group) and donor-level pseudobulk DESeq2 with `pool + sex + age + null_group`.

All 10/10 allocations produced zero discoveries at FDR < 0.05. Between 16,067 and 16,075 genes were tested per allocation.

The allocations heavily reuse donors: 449 occur in every allocation and pairwise overlap is 451-454 of 454. They are not independent cohorts. The result supports calibration in this well-powered setting; it does not establish a zero false-positive rate or externally validate the governance effect.

pyDESeq2 emitted optimizer RuntimeWarnings in worker processes. Every fit completed Wald testing; all six final result columns were finite for seeds 3001-3009. Seed 3000 predates that diagnostic. Worker-warning counts saved as zero are not interpreted.
