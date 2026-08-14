# Null Diagnostic Sensitivity Report

- Dataset: tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
- Cell type: fenestrated cell
- Valid allocations analyzed: 18

## Discovery Stability

- Null discoveries: {'n': 18, 'mean': 224.7222, 'median': 221.5, 'q1': 210.0, 'q3': 232.0, 'min': 172.0, 'max': 295.0}
- Pairwise gene Jaccard: {'n': 153, 'mean': 0.0599, 'median': 0.0239, 'q1': 0.0152, 'q3': 0.0466, 'min': 0.0023, 'max': 0.3955}
- Nearest-partition discovery difference: {'n': 18, 'mean': 33.1111, 'median': 35.0, 'q1': 16.25, 'q3': 45.5, 'min': 1.0, 'max': 64.0}
- Nearest-partition gene Jaccard: {'n': 18, 'mean': 0.3055, 'median': 0.3106, 'q1': 0.2731, 'q3': 0.3282, 'min': 0.2278, 'max': 0.3955}

## Donor Exclusion

| Donor | Excluded n | Excluded mean | Retained n | Retained mean | Difference |
|---|---:|---:|---:|---:|---:|
| 18_46_F | 6 | 208.3333 | 12 | 232.9167 | -24.5833 |
| 24_58_M | 0 | None | 18 | 224.7222 | None |
| 24_59_M | 0 | None | 18 | 224.7222 | None |
| 24_60_M | 0 | None | 18 | 224.7222 | None |
| 24_61_M | 0 | None | 18 | 224.7222 | None |
| 3_11_M | 6 | 246.8333 | 12 | 213.6667 | 33.1667 |
| 3_38_F | 6 | 219.0 | 12 | 227.5833 | -8.5833 |

## Interpretation Boundary

Exhaustive valid-partition sensitivity. Literal leave-one-donor-out refits were not run because removing one donor from a 3-vs-3 design creates an inadmissible 2-vs-3 DESeq2 comparison.

PCA distance and partition sensitivity identify influential donor profiles; they do not establish a causal technical defect in a donor.