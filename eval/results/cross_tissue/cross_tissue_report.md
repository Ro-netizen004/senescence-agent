# Cross-Tissue TMS Validation Report

## Datasets

- Tissues attempted: 5
- Tissues completed: 5 / 5

## Results

### Coverage and Scoring

| Tissue | Cells | Coverage % | Genes Used | Mean Score | Max Score |
|--------|-------|-----------|------------|------------|-----------|
| Kidney | 1,833 | 90.3 | 112 | 0.0355 | 0.9277 |
| Liver | 2,859 | 90.3 | 112 | 0.0572 | 0.6011 |
| Spleen | 3,834 | 90.3 | 112 | -0.0056 | 0.9608 |
| Aorta | 906 | 90.3 | 112 | 0.0994 | 0.5977 |
| Limb_Muscle | 3,855 | 90.3 | 112 | 0.1243 | 0.8993 |

### Age Trends (youngest vs oldest)

| Tissue | Youngest | Oldest | Young Median | Old Median | Trend |
|--------|----------|--------|--------------|------------|-------|
| Kidney | 3m | 24m | 0.0551 | 0.0355 | decreasing |
| Liver | 3m | 24m | 0.0525 | 0.0633 | increasing |
| Spleen | 3m | 24m | -0.0015 | -0.0095 | decreasing |
| Aorta | 3m | 24m | 0.0702 | 0.0603 | decreasing |
| Limb_Muscle | 3m | 24m | 0.1406 | 0.1199 | decreasing |

### Top Senescent Cell Types per Tissue

| Tissue | Top Cell Type | Top 3 |
|--------|--------------|-------|
| Kidney | macrophage | macrophage, mesangial cell, fenestrated cell |
| Liver | neutrophil | neutrophil, endothelial cell of hepatic sinusoid, Kupffer cell |
| Spleen | granulocyte | granulocyte, NK cell, proerythroblast |
| Aorta | fibroblast of cardiac tissue | fibroblast of cardiac tissue, professional antigen presenting cell, fibrocyte |
| Limb_Muscle | mesenchymal stem cell | mesenchymal stem cell, macrophage, endothelial cell |

## Notes

- All datasets: TMS FACS processed official annotations (Tabula Muris Consortium 2020)
- Species: mouse
- Signature: SenMayo 125-gene set (Saul et al. 2022)
- **Scores are relative within each dataset — not directly comparable across tissues**
- Age trend: global median senescence score comparing youngest vs oldest age group
- **Age trends are descriptive only.** Global medians are confounded by age-related shifts in cell-type composition. A tissue where a high-scoring cell type becomes less abundant with age will show a decreasing global trend even if per-cell senescence increases. Cell-type-specific analysis is required to disentangle composition from true senescence accumulation.
- Top senescent cell types are ranked by per-cell-type median score (same source as top-3 column)
- Statistical testing (Mann-Whitney on per-sample medians) not run here — see gold case eval for per-tissue p-values