# Same-method Governance Ablation: TMS Multi-tissue Null Pilot

**Status: paper-usable pilot; external many-donor validation required.**

| Tissue | Pairs | Governed mean discoveries | Ungoverned mean discoveries | Governed overclaim | Ungoverned overclaim |
|---|---:|---:|---:|---:|---:|
| Kidney | 6 | 458.67 | 458.67 | 0% | 100% |
| Liver | 8 | 30.12 | 30.12 | 0% | 62% |
| Spleen | 30 | 53.67 | 53.67 | 0% | 90% |
| Aorta | 4 | 190.50 | 190.50 | 0% | 100% |
| Limb_Muscle | 30 | 166.47 | 166.47 | 0% | 100% |

Across 78 matched allocations, governed reply overclaim was 0/78 (0.0%), versus 72/78 (92.3%) ungoverned.

Governance withheld gene-level results in 78/78 allocations; the ungoverned arm withheld them in 4/78.

Allocations reuse donors and therefore are not independent biological experiments; no biological-population confidence interval or paired p-value is claimed. Raw discovery counts are descriptive diagnostics, not proven gene-level false positives.

Both arms use identical donor-level pseudobulk DESeq2 results. The aggregator refuses output if allocation, discovery count, significant genes, design, or covariates differ. External many-donor UMI validation is still required.
