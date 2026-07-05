# Null Harness Sweep - Summary

Configurations: 13 | permutations each: 200

| Tissue | Cell type | Mice | Genes | Per-cell FP (FDR) | Pseudobulk FP (FDR) | Ungoverned FDR rate | Governed FDR rate |
|--------|-----------|-----:|------:|------------------:|--------------------:|--------------------:|------------------:|
| Kidney | epithelial cell of proximal tubule | 7 | 5333 | **916** | 0.0 | 100% | 1% |
| Kidney | fenestrated cell | 7 | 5867 | **221** | 0.0 | 100% | 2% |
| Kidney | kidney collecting duct epithelial cell | 6 | 5176 | **708** | 0.1 | 100% | 9% |
| Liver | hepatocyte | 9 | 9104 | **5748** | 0.7 | 100% | 1% |
| Liver | endothelial cell of hepatic sinusoid | 6 | 7075 | **1161** | 0.0 | 100% | 0% |
| Liver | B cell | 4 | 4741 | **63** | 0.0 | 100% | 0% |
| Spleen | B cell | 13 | 5514 | **2291** | 0.0 | 100% | 2% |
| Spleen | CD4-positive, alpha-beta T cell | 12 | 5629 | **201** | 0.0 | 100% | 1% |
| Spleen | CD8-positive, alpha-beta T cell | 9 | 6113 | **291** | 0.1 | 100% | 3% |
| Aorta | aortic endothelial cell | 7 | 6007 | **883** | 0.0 | 100% | 4% |
| Limb_Muscle | skeletal muscle satellite cell | 13 | 5005 | **2877** | 4.9 | 100% | 5% |
| Limb_Muscle | mesenchymal stem cell | 12 | 7045 | **2570** | 0.3 | 100% | 3% |
| Limb_Muscle | endothelial cell | 10 | 4458 | **593** | 0.0 | 100% | 2% |

**Mean per-cell false-positive genes (FDR): 1425**
**Mean pseudobulk false-positive genes (FDR): 0.47**

Truth = 0 DE genes (constructed null). Per-cell = ungoverned; pseudobulk = governed.