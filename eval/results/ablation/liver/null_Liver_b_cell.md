# Null Harness (gene-level) - Pseudoreplication False Discovery

## Setup

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Liver.h5ad
- Cell type: B cell
- Biological replicates (mice): 4 (groups of 2)
- Genes tested: 4741
- Null permutations: 200
- alpha = 0.05

**Truth: null (random mouse-to-group split of one population); expected DE genes = 0.** Every reported DE gene is a false positive.

## Layer 1 - false-positive genes per null split

| Method | Statistical unit | FP genes (raw p<0.05) | FP genes (FDR<0.05) |
|--------|------------------|----------------------:|--------------------:|
| Per-cell Wilcoxon (ungoverned) | cell | 695.33 | **63.41** |
| Pseudobulk t-test (governed) | biological replicate | 104.61 | 0.0 |

## Layer 2 - agent false-discovery rate

- Ungoverned agent reports >=1 DE gene on **100.0%** of null splits
- Governed agent reports >=1 DE gene on **0.0%** of null splits

## Interpretation

On data with no real difference, the per-cell test treats correlated cells within a mouse as independent observations and reports large numbers of false-positive genes - the pseudoreplication failure (Squair et al. 2021). An ungoverned agent that runs per-cell differential expression reports these as discoveries. The governed agent aggregates to biological replicates (pseudobulk), collapsing the false discoveries to near zero.