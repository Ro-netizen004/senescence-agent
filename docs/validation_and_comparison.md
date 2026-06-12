# Validation & Comparison Slide Content

## Validation Slide (GSE226225)

### What This Slide Shows

We ran our agent on GSE226225 -- a published dataset where senescent cells are **explicitly labeled** by the original researchers. This is a held-out validation: our tool did not train on this data.

### How to Generate the Data

Rodela runs this analysis in Week 4 using the agent's `senescence_score` tool on the GSE226225 dataset. The key metric is **overlap** between:
- Cells our SenMayo scoring flags as high-senescence (top quartile of scores)
- Cells the original researchers labeled as senescent

### Slide Template

```
VALIDATION ON HELD-OUT DATASET

Dataset: GSE226225 (published senescence labels)
Method:  SenMayo 125-gene signature scoring

Result:  Our tool identified [X]% of labeled senescent cells
         (sensitivity) with [Y]% precision.

         [Side-by-side UMAP: original labels vs. our scores]

"This is not a demo -- it is a scientific result."
```

### How to Compute Overlap

```python
import scanpy as sc
import numpy as np

adata = sc.read_h5ad("GSE226225.h5ad")

# Step 1: Run SenMayo scoring (agent does this)
# senescence_score tool adds 'senescence_score' to adata.obs

# Step 2: Threshold for "senescent" call
threshold = np.percentile(adata.obs["senescence_score"], 75)  # top 25%
adata.obs["predicted_senescent"] = adata.obs["senescence_score"] > threshold

# Step 3: Compare with published labels
# (column name depends on dataset -- check adata.obs.columns)
published_col = "senescence_label"  # adjust as needed

true_positives = (
    (adata.obs["predicted_senescent"] == True) &
    (adata.obs[published_col] == "senescent")
).sum()

total_labeled = (adata.obs[published_col] == "senescent").sum()
total_predicted = (adata.obs["predicted_senescent"] == True).sum()

sensitivity = true_positives / total_labeled * 100
precision = true_positives / total_predicted * 100

print(f"Sensitivity: {sensitivity:.1f}%")
print(f"Precision: {precision:.1f}%")
```

Even 60-70% overlap is impressive and publishable. The key message: **a multi-gene signature outperforms any single marker.**

---

## Comparison Table Slide

### What This Slide Shows

On the same set of cells, compare three senescence detection methods side by side. This answers the judge question: "Why use SenMayo instead of just p16?"

### Methods Compared

| Method | Description | Expected Strengths | Expected Weaknesses |
|--------|-------------|-------------------|---------------------|
| (a) CDKN2A threshold | Cells with CDKN2A > median are "senescent" | Simple, widely used | Misses cell types where p16 is silenced |
| (b) MKI67 absence | Cells with MKI67 = 0 are "growth-arrested" | Catches all non-dividing cells | Many false positives (quiescent != senescent) |
| (c) SenMayo score | Full 125-gene signature, top quartile | Multi-dimensional, validated | Requires more genes present |

### How to Generate the Data

```python
import scanpy as sc
import numpy as np
import pandas as pd

adata = sc.read_h5ad("GSE226225.h5ad")  # or any dataset with senescence labels

# Published labels
published_col = "senescence_label"  # adjust as needed
true_senescent = adata.obs[published_col] == "senescent"

# Method A: CDKN2A threshold
if "Cdkn2a" in adata.var_names:  # mouse
    gene = "Cdkn2a"
elif "CDKN2A" in adata.var_names:  # human
    gene = "CDKN2A"

cdkn2a_expr = adata[:, gene].X.toarray().flatten() if hasattr(adata[:, gene].X, 'toarray') else adata[:, gene].X.flatten()
pred_a = cdkn2a_expr > np.median(cdkn2a_expr)

# Method B: MKI67 absence
mki67_gene = "Mki67" if "Mki67" in adata.var_names else "MKI67"
mki67_expr = adata[:, mki67_gene].X.toarray().flatten() if hasattr(adata[:, mki67_gene].X, 'toarray') else adata[:, mki67_gene].X.flatten()
pred_b = mki67_expr == 0

# Method C: SenMayo score (already computed by agent)
threshold_c = np.percentile(adata.obs["senescence_score"], 75)
pred_c = adata.obs["senescence_score"].values > threshold_c

# Compute metrics for each
results = []
for name, pred in [("CDKN2A only", pred_a), ("MKI67 absence", pred_b), ("SenMayo (ours)", pred_c)]:
    tp = (pred & true_senescent).sum()
    fp = (pred & ~true_senescent).sum()
    fn = (~pred & true_senescent).sum()
    sensitivity = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    f1 = 2 * (precision * sensitivity) / (precision + sensitivity) if (precision + sensitivity) > 0 else 0
    results.append({"Method": name, "Sensitivity": f"{sensitivity:.1f}%", "Precision": f"{precision:.1f}%", "F1": f"{f1:.1f}%"})

df = pd.DataFrame(results)
print(df.to_markdown(index=False))
```

### Slide Template

```
WHY SENMAYO? -- METHOD COMPARISON

Same cells, three detection approaches:

| Method            | Sensitivity | Precision | F1 Score |
|-------------------|-------------|-----------|----------|
| CDKN2A (p16) only | [X]%        | [Y]%      | [Z]%    |
| MKI67 absence     | [X]%        | [Y]%      | [Z]%    |
| SenMayo (ours)    | [X]%        | [Y]%      | [Z]%    |

Key insight: Single markers miss entire categories of
senescent cells. The full signature captures the
multi-dimensional senescence phenotype.
```

### Talking Points

- "p16 is the gold standard single marker, but it's silenced in some cell types"
- "MKI67 absence catches all non-dividing cells, including quiescent stem cells -- too many false positives"
- "SenMayo uses 125 genes covering growth arrest, SASP, nuclear changes, and DNA damage response"
- "This is why the field moved toward multi-gene signatures -- no single gene captures the full phenotype"
