# OneK1K External Validation

## Dataset source

The analyzed file, `OneK1K_updated_14_celltypes_980_donors.h5ad`, was
downloaded from [Zenodo record 18870747](https://zenodo.org/records/18870747)
(version DOI `10.5281/zenodo.18870747`; concept DOI
`10.5281/zenodo.18870746`) under CC BY 4.0 in August 2026. The registered file
MD5 is `a16487819c21506b400cd1d36f09c3e1`. The H5AD itself is intentionally not
stored in this repository.

## Current status

Seed 3000 is the completed direct statistical smoke, not the final multi-seed
external-validation result. It used 454 independent classical-monocyte donors
(227 per fake group), tested 16,071 genes, and produced 0 discoveries at
FDR < 0.05.

## Files

- `smoke_seed3000/summary.json`: compact analysis output and the top 100 rows.
- `smoke_seed3000/donor_allocation.csv`: complete frozen donor assignment.
- The 2.9 GB H5AD is intentionally excluded from Git and remains on `D:`.

## Numerical warning record

pyDESeq2 emitted `overflow encountered in exp` and related invalid-value
warnings during coefficient optimization. The fit nevertheless completed the
Wald tests and returned no FDR discoveries (minimum saved adjusted p-value
0.9999897). Because this run used `--summary-only`, a full-table post-hoc
finite-value audit is unavailable. The runner now records warning text and
finite/nonfinite counts under `numerical_health` for all subsequent runs.

## Next gate

Run `paired_frozen_smoke.py` once. It performs no DE computation and makes
exactly one LLM call, for the ungoverned narration. Both arms are keyed to the
same canonical SHA-256 of the frozen result. This is a communication-layer
smoke only; the later multi-seed validation must exercise the full agent path.

The seed-3000 paired replay completed with input parity. Its initial linter
label was a false positive on "No genes are statistically significant"; after
the negation regression fix, `paired_frozen_smoke.rescored.json` is the
canonical scored artifact. Both arms have zero claim violations. This is the
expected outcome when the shared pseudobulk result itself has zero discoveries,
so it validates plumbing and calibration but does not estimate a governance
effect.

## Ten-allocation pilot

The completed statistical pilot is packaged at
`pilot_null_monoc_seed3000_n10/`. It contains validated compact raw checkpoints,
an aggregate CSV/JSON/Markdown result set, provenance, and recursive checksums.
All ten allocations returned zero FDR discoveries. No additional LLM narration
calls were made because a zero-discovery shared result cannot meaningfully test
the governance-withholding endpoint.

## Semi-synthetic positive control

The five-allocation positive-control package is at
`semisynthetic_positive_monoc_seed4000_n5/`. Across 375 registered donor-level
effects, 358 were recovered (95.47% sensitivity), with 100% effect-direction
agreement, 11 additional discoveries (pooled empirical FDP 2.98%), donor
stability in 5/5 allocations, and `SIGNIFICANT_INFERENTIAL` licensing in 5/5.
This is the selectivity control showing that governance does not merely suppress
all findings. The allocations reuse the same donor cohort and are not
independent biological cohorts. This package is the deterministic statistical-
governance result; it does not exercise LLM routing or narration.

## Full-agent semi-synthetic positive control

The matched agent-level package is at
`full_agent_positive_monoc_seed4000_n5/`. The governed production agent and
ungoverned ablation each independently routed and executed the registered
DESeq2 analysis for five allocations. Both arms routed correctly in 5/5,
statistical outputs matched exactly in 5/5, governed LLM plans were accepted in
5/5, and both arms communicated the supported signal in 5/5. Governance
licensed all five results as `SIGNIFICANT_INFERENTIAL`.

The agent received a lossless donor-pseudobulk AnnData evaluation adapter, so
routing, planning, admissibility, DESeq2 execution, inference-state assignment,
and communication were exercised. Raw-cell upload and the initial OneK1K
pseudobulk build were not independently repeated in each arm.

## Full-agent null validation

The matched agent-level package is at `full_agent_null_monoc_seed3000_n10/`.
Across ten registered donor splits, both governed and ungoverned agents routed
and independently executed the same donor-level pseudobulk DESeq2 analysis.
Routing, exact statistical parity, and reproduction of the registered
zero-discovery result occurred in 10/10 pairs. Governed plans were accepted and
assigned `NOT_SIGNIFICANT` in 10/10; both arms explicitly communicated the null
in 10/10, with no positive significance claim in any of 20 replies.

This upgrades the OneK1K null from method-only calibration to full-agent
routing, execution, and communication validation. It does not estimate a
governance withholding advantage because all underlying outputs contained zero
discoveries. The allocations also reuse one donor cohort.
