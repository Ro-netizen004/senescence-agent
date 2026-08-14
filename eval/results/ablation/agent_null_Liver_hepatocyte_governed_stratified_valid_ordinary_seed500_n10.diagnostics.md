# Null Diagnostic Sensitivity Report

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Liver.h5ad
- Cell type: hepatocyte
- Valid allocations analyzed: 8

## Discovery Stability

- Null discoveries: {'n': 8, 'mean': 15.0, 'median': 9.5, 'q1': 8.75, 'q3': 18.0, 'min': 7.0, 'max': 37.0}
- Pairwise gene Jaccard: {'n': 28, 'mean': 0.0584, 'median': 0.0427, 'q1': 0.0, 'q3': 0.092, 'min': 0.0, 'max': 0.3261}
- Nearest-partition discovery difference: {'n': 16, 'mean': 10.625, 'median': 8.5, 'q1': 2.0, 'q3': 16.25, 'min': 0.0, 'max': 28.0}
- Nearest-partition gene Jaccard: {'n': 16, 'mean': 0.0851, 'median': 0.0754, 'q1': 0.0, 'q3': 0.1063, 'min': 0.0, 'max': 0.3261}

## Donor Exclusion

| Donor | Excluded n | Excluded mean | Retained n | Retained mean | Difference |
|---|---:|---:|---:|---:|---:|
| 18_45_M | 0 | None | 8 | 15.0 | None |
| 18_46_F | 8 | 15.0 | 0 | None | None |
| 18_53_M | 0 | None | 8 | 15.0 | None |
| 24_58_M | 0 | None | 8 | 15.0 | None |
| 24_59_M | 0 | None | 8 | 15.0 | None |
| 3_11_M | 0 | None | 8 | 15.0 | None |
| 3_56_F | 0 | None | 8 | 15.0 | None |
| 3_57_F | 0 | None | 8 | 15.0 | None |
| 3_9_M | 0 | None | 8 | 15.0 | None |

## Interpretation Boundary

Exhaustive valid-partition sensitivity. Literal leave-one-donor-out refits were not run because removing one donor from a 3-vs-3 design creates an inadmissible 2-vs-3 DESeq2 comparison.

PCA distance and partition sensitivity identify influential donor profiles; they do not establish a causal technical defect in a donor.