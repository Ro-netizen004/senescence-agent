# GSE226225 Validation Report

## Dataset
- **Source:** GEO GSE226225
- **Shape:** 55317 cells x 33207 genes
- **Species:** human (WI-38 fibroblasts)
- **Label column:** published_senescent
- **Label definition:** CTRL/day0 = non-senescent; RS/IR/ETO timepoints = senescent
- **Gene naming:** Human symbols (CDKN1A, CDKN2A, etc.)

## SenMayo Results
- **Coverage:** 98.4% (122 genes used)
- **AUROC:** 0.5632 (threshold-independent)
- **AUPRC:** 0.8612 (threshold-independent)
- **Threshold:** Top 25% of SenMayo scores (value: 0.2464)
- **Sensitivity:** 30.1%
- **Precision:** 94.2%
- **F1 Score:** 45.6%

### Confusion Matrix
|  | Predicted Senescent | Predicted Non-senescent |
|--|--:|--:|
| **True Senescent** | 13028 (TP) | 30252 (FN) |
| **True Non-senescent** | 802 (FP) | 11235 (TN) |

## Marker Comparison

| method            |   auroc |   sensitivity |   precision |     f1 |    tp |   fp |    fn |
|:------------------|--------:|--------------:|------------:|-------:|------:|-----:|------:|
| CDKN2A (p16) only |  0.5055 |        0.4838 |      0.757  | 0.5903 | 20938 | 6720 | 22342 |
| MKI67 absence     |  0.7975 |        0.9466 |      0.9038 | 0.9247 | 40971 | 4363 |  2309 |
| SenMayo (ours)    |  0.5632 |        0.301  |      0.942  | 0.4562 | 13028 |  802 | 30252 |

## UMAP
See `gse226225_umap.png` for side-by-side comparison of:
1. SenMayo score distribution
2. Published senescence labels
3. SenMayo top-25% predictions

## Notes / Limitations
- **Label interpretation:** CTRL cells are labeled non-senescent; RS, IR, and ETO-treated cells are labeled senescent. ETO day-0 is treated as non-senescent (treatment not yet active).
- **Threshold choice:** Top 25% is a simple first-pass threshold. AUROC/AUPRC would give a threshold-independent evaluation.
- **Cell type:** All cells are WI-38 fibroblasts (single cell type), so cell-type confounding is not an issue.
- **SenMayo coverage:** Not all 125 SenMayo genes may be expressed in WI-38 fibroblasts.
