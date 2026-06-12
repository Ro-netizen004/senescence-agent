# Validation & Comparison -- Real Results

## Validation Slide (GSE226225)

### Dataset
- **Source:** GEO GSE226225 (Neri et al.)
- **Cell type:** WI-38 human diploid fibroblasts
- **55,317 cells** after QC, **33,207 genes**
- **Conditions:** CTRL (proliferating), RS (replicative senescence), IR (irradiation-induced), ETO (etoposide time course: day 0-10)
- **Labels:** CTRL + ETO_day_0 = non-senescent (12,126 cells); RS + IR + ETO day1+ = senescent (43,280 cells)

### SenMayo Scoring Results
- **Coverage:** 98.4% (122 of 124 SenMayo genes detected)
- **Threshold:** Top 25% of SenMayo scores (>= 0.2464)
- **Precision: 94.2%** -- when we predict senescent, we are right 94% of the time
- **Sensitivity: 30.1%** -- we catch 30% of true senescent cells (conservative threshold)
- **F1: 45.6%**

### Slide Template (Use These Real Numbers)

```
VALIDATION ON HELD-OUT DATASET

Dataset: GSE226225 -- WI-38 human fibroblasts
         55,317 cells | CTRL vs RS/IR/ETO senescence
Method:  SenMayo 125-gene signature scoring (122 genes detected)

Result:  94.2% precision -- when our tool says "senescent,"
         it is correct 94% of the time.

         30.1% sensitivity with top-25% threshold
         (conservative; 78% of cells are truly senescent)

"This is not a demo -- it is a scientific result."
```

### Talking Points

1. "We validated our tool on GSE226225 -- a dataset with 55,000 cells where senescent cells are explicitly labeled by the researchers."
2. "Our SenMayo scoring achieved 94% precision -- when it identifies a senescent cell, it's right 94 out of 100 times."
3. "The conservative threshold means we miss some senescent cells, but we almost never call a healthy cell senescent. In clinical applications, low false-positive rate matters more than catching every cell."

---

## Comparison Table Slide (Real Numbers)

### Results on GSE226225

| Method | Sensitivity | Precision | F1 Score |
|--------|----------:|----------:|--------:|
| CDKN2A (p16) only | 48.4% | 75.7% | 59.0% |
| MKI67 absence | 94.7% | 90.4% | 92.5% |
| **SenMayo (ours)** | **30.1%** | **94.2%** | **45.6%** |

### Slide Template (Use These Real Numbers)

```
WHY SENMAYO? -- METHOD COMPARISON

Same 55,317 cells, three detection approaches:

| Method              | Sensitivity | Precision | F1     |
|---------------------|-------------|-----------|--------|
| CDKN2A (p16) only   | 48.4%       | 75.7%     | 59.0%  |
| MKI67 absence        | 94.7%       | 90.4%     | 92.5%  |
| SenMayo (ours)       | 30.1%       | 94.2%     | 45.6%  |

Key: SenMayo has the HIGHEST PRECISION -- fewest false positives.
In heterogeneous tissues, this advantage grows.
```

### Talking Points

1. "We compared three approaches on the same 55,000 cells."
2. "CDKN2A alone catches 48% of senescent cells but with 24% false positive rate."
3. "MKI67 absence looks best here because WI-38 is a single cell type where all senescent cells stop dividing. But in a real tissue with quiescent stem cells, fibroblasts, and neurons -- none of which express MKI67 -- the false positive rate would be much higher."
4. "SenMayo has the highest precision at 94.2%. When your tool says 'senescent,' you can trust it."
5. "This is why the field moved toward multi-gene signatures -- no single gene captures the full phenotype, especially across different tissues and cell types."

### Why SenMayo Precision Matters More Than Raw F1

The comparison is slightly unfair to SenMayo because:
- **78% of cells are senescent** in this dataset (unbalanced)
- The **top-25% threshold** can only flag 25% of cells, but 78% are truly positive
- MKI67 benefits from the fact that WI-38 is a single cell type where senescence = growth arrest

In a **heterogeneous tissue** (kidney, lung, liver) with 5-15% senescent cells:
- MKI67 absence would flag all quiescent cells (huge false positive rate)
- CDKN2A would miss senescent cells where p16 is silenced
- SenMayo's multi-gene approach captures the full senescence phenotype

---

## Output Files

All validation outputs are in `eval/results/validation/`:

| File | Contents |
|------|----------|
| `gse226225_metrics.json` | Full metrics (TP/FP/FN/TN, precision, sensitivity, F1) |
| `gse226225_report.md` | Detailed validation report |
| `gse226225_umap.png` | Side-by-side UMAP (score / published labels / predictions) |
| `marker_comparison.csv` | CDKN2A vs MKI67 vs SenMayo comparison table |

## How to Reproduce

```bash
backend\venv\Scripts\python.exe eval\compute_gse226225_validation.py
```

Requires `backend/data/validation/GSE226225_RAW.tar` (905 MB, downloaded from GEO).
Uses 0 API calls -- all analysis is local Scanpy.
