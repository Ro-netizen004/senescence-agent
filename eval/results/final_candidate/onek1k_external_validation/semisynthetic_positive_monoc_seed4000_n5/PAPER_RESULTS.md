# OneK1K Semi-synthetic Positive Control

**Status: paper-candidate selectivity validation.** Five registered allocations completed under protocol `onek1k_semisynthetic_v2`. No LLM API calls were made.

## Question

Does the validity firewall preserve and license reproducible signal, rather than simply withholding every result?

## Design

Classical-monocyte raw UMI counts from OneK1K were aggregated by biological donor. Each allocation retained 454 donors (227 per artificial group), paired within pool/sex strata and by adjacent ages. We injected 25 balanced up/down donor-level effects at each absolute log2 fold-change tier 0.25, 0.50, and 1.00. The production admissibility, pseudobulk DESeq2, plausibility, leave-one-donor-out stability, and inference-state functions were then run without an LLM.

## Results

| Endpoint | Result |
|---|---:|
| Completed allocations | 5/5 |
| Admissible allocations | 5/5 |
| `SIGNIFICANT_INFERENTIAL` allocations | 5/5 |
| Registered effects | 375 |
| Recovered effects | 358/375 (95.47%) |
| Missed effects | 17 |
| Additional discoveries | 11 |
| Pooled empirical FDP | 2.98% |
| Direction agreement among recovered effects | 100% |
| Donor-stable allocations | 5/5 |
| Runtime warnings | 0 |

### Recovery by effect tier

| Absolute injected log2FC | Recovered | Sensitivity |
|---:|---:|---:|
| 0.25 | 109/125 | 87.2% |
| 0.50 | 124/125 | 99.2% |
| 1.00 | 125/125 | 100% |

## Interpretation

The firewall did not behave as a blanket refusal mechanism. Every valid injected-signal design passed admissibility, every allocation was donor-stable, and all five were licensed as `SIGNIFICANT_INFERENTIAL`. Recovery increased with effect size and all recovered effects had the registered direction.

## Limitations

The five allocations reuse a single eligible donor cohort and are not five independent biological cohorts. Registered genes and group orientations vary by seed. The empirical FDP is descriptive for this benchmark and does not establish universal DESeq2 calibration. This experiment tests deterministic statistical selectivity, not LLM routing or narration.

Primary numerical evidence is in `paper_summary.json` and `per_seed_summary.csv`; sanitized allocation records are under `raw/`.
