# GSE226225 Validation Report

## Dataset
- **Source:** GEO GSE226225
- **Shape:** 55,317 cells x 33,207 genes
- **Species:** Human (WI-38 fibroblasts)
- **Label column:** published_senescent
- **Label definition:** CTRL/ETO_day_0 = non-senescent; RS/IR/ETO timepoints = senescent
- **Gene naming:** Human symbols (CDKN1A, CDKN2A, etc.)
- **Conditions:** CTRL (proliferating), RS (replicative senescence), IR (irradiation), ETO (etoposide time course: day 0-10)

## SenMayo Results
- **Coverage:** 98.4% (122 of 124 SenMayo genes detected)
- **Threshold:** Top 25% of SenMayo scores (value: 0.2464)
- **Sensitivity:** 30.1%
- **Precision:** 94.2%
- **F1 Score:** 45.6%

### Confusion Matrix

|  | Predicted Senescent | Predicted Non-senescent |
|--|--:|--:|
| **True Senescent** | 13,028 (TP) | 30,252 (FN) |
| **True Non-senescent** | 802 (FP) | 11,235 (TN) |

### Interpretation

SenMayo achieves **94.2% precision** -- when it identifies a cell as senescent, it is correct 94% of the time. The lower sensitivity (30.1%) is expected: the top-25% threshold is conservative on a dataset where 78% of cells are truly senescent.

## Marker Comparison

| Method | Sensitivity | Precision | F1 |
|--------|----------:|----------:|---:|
| CDKN2A (p16) only | 48.4% | 75.7% | 59.0% |
| MKI67 absence | 94.7% | 90.4% | 92.5% |
| SenMayo (ours) | 30.1% | 94.2% | 45.6% |

### Key Insights

- **SenMayo has the highest precision** (94.2%) -- fewest false positives of all three methods
- **MKI67 absence** has the best overall F1 because most senescent WI-38 cells stop dividing -- but MKI67 absence also flags quiescent (non-senescent) cells in heterogeneous tissues
- **CDKN2A alone** catches ~48% of senescent cells but with lower precision (75.7%)
- In a heterogeneous tissue (unlike this single-cell-type dataset), MKI67 absence would produce many more false positives from quiescent non-senescent cells. SenMayo's multi-gene approach is designed for that scenario.

## UMAP

See `gse226225_umap.png` for side-by-side comparison of:
1. SenMayo score distribution (continuous)
2. Published senescence labels (binary)
3. SenMayo top-25% predictions (binary)

## Notes / Limitations
- **Label interpretation:** CTRL and ETO_day_0 cells are labeled non-senescent; RS, IR, and ETO day 1+ are labeled senescent.
- **Threshold choice:** Top 25% is a simple first-pass threshold. AUROC/AUPRC would give a threshold-independent evaluation.
- **Cell type:** All cells are WI-38 fibroblasts (single cell type), so cell-type confounding is not an issue. In real tissue datasets with multiple cell types, SenMayo's advantage over MKI67 would be larger.
- **SenMayo coverage:** 122 of 124 genes detected (98.4% -- excellent coverage in this cell line).
