# Senescence Agent -- SKILL.md

## When to Use This Skill

Use when a researcher uploads a single-cell RNA-seq dataset (.h5ad) and asks questions about cellular senescence, aging, or gene expression changes with age. The agent specializes in detecting and quantifying senescent cell populations using the SenMayo gene signature.

## Available Tools

### 1. `find_senescence_markers`

Check which SenMayo senescence genes are present in the uploaded dataset.

**Arguments:** None (uses dataset and species from session)

**Example call:**
```
"Which senescence markers are in my dataset?"
```

**Returns:** List of found/missing markers, coverage percentage.

---

### 2. `senescence_score`

Score every cell against the SenMayo 125-gene signature. Higher score = more senescent phenotype.

**Arguments:** None

**Example call:**
```
"Score the cells for senescence"
"Run SenMayo scoring"
```

**Returns:** Per-cluster mean scores, top senescent cluster/cell type, UMAP colored by score.

---

### 3. `generate_umap`

Generate a 2D UMAP visualization colored by Leiden cluster.

**Arguments:** None

**Example call:**
```
"Show me a UMAP"
"Visualize the clusters"
```

**Returns:** Path to saved UMAP PNG.

---

### 4. `get_cluster_annotations`

Map each Leiden cluster to its dominant cell type (from `cell_ontology_class`).

**Arguments:** None

**Example call:**
```
"What cell types are in each cluster?"
```

**Returns:** Cluster-to-cell-type mapping with distribution percentages.

---

### 5. `compare_across_age`

Compare SenMayo scores across age groups, optionally filtered by cell type.

**Arguments:**
- `cell_type` (optional): Restrict to one cell type (e.g., "T cell", "macrophage")
- `reference_age` (optional): Young group (e.g., "3m")
- `comparison_age` (optional): Old group (e.g., "24m")

**Example calls:**
```
"How does senescence change with age?"
"Compare senescence in macrophages between 3m and 24m"
```

**Returns:** Median scores by age group, cell-type stratification, violin plots. Descriptive only -- no p-values.

---

### 6. `test_senescence_difference`

Statistical test (Mann-Whitney U) for SenMayo score differences between two age groups in one cell type. Uses per-sample medians, not per-cell values.

**Arguments:**
- `cell_type` (required): e.g., "T cell"
- `reference_age`: e.g., "3m"
- `comparison_age`: e.g., "24m"

**Example calls:**
```
"Is the senescence difference in T cells significant?"
"What is the p-value for senescence in macrophages, 3m vs 24m?"
```

**Returns:** p-value, effect size, sample counts, inference state (A-E).

---

### 7. `run_deseq2`

Pseudobulk differential expression analysis using DESeq2. Identifies genes that change between age groups for a specific cell type.

**Arguments:**
- `cell_type` (required): e.g., "macrophage"
- `reference_age` (optional): e.g., "3m"
- `comparison_age` (optional): e.g., "24m"

**Example calls:**
```
"Which genes change with age in T cells?"
"Run DESeq2 for macrophages"
```

**Returns:** Ranked gene list with log2FC, padj, FDR significance.

---

## Senescence Marker Gene List

These genes are hardcoded into the agent's SenMayo signature:

| Gene (Human) | Mouse Ortholog | Role | Signal |
|--------------|---------------|------|--------|
| CDKN1A | Cdkn1a | p21 -- cell cycle arrest | High = senescent |
| CDKN2A | Cdkn2a | p16/INK4a -- strongest single marker | High = senescent |
| IL6 | Il6 | SASP inflammatory cytokine | Co-elevated with IL8 |
| IL8/CXCL8 | Cxcl15 | SASP inflammatory cytokine | Co-elevated with IL6 |
| LMNB1 | Lmnb1 | Nuclear lamina | Low/absent = senescent |
| TP53 | Trp53 | DNA damage response | Elevated after damage |
| MKI67 | Mki67 | Proliferation marker | Absent = growth arrested |
| SERPINE1 | Serpine1 | PAI-1, SASP component | Elevated |
| GLB1 | Glb1 | SA-beta-Gal, lysosomal | Classic marker |
| HMGA1 | Hmga1 | Chromatin remodeling | Increased in replicative senescence |

Full SenMayo signature: 125 genes loaded from `backend/data/senmayo.json`.

## Species Gene Name Rule

- Human datasets: uppercase (CDKN1A, IL6, TP53)
- Mouse datasets: title-case with special mappings (Cdkn1a, Il6, Trp53)
- All tools use the `species` parameter from the session
- Conversion handled automatically by `gene_utils.py`

## Common Workflows

### Quick senescence check
```
"Run the full senescence analysis"
```
Runs: find_senescence_markers -> senescence_score -> generate_umap -> get_cluster_annotations -> compare_across_age

### Statistical test for one cell type
```
"Is the senescence difference in T cells between young and old mice significant?"
```
Runs: test_senescence_difference (cell_type="T cell", reference_age="3m", comparison_age="24m")

### Gene-level aging analysis
```
"Which genes change with age in macrophages?"
```
Runs: run_deseq2 (cell_type="macrophage")

### Full exploration pipeline
```
"Run everything, then test T cells and macrophages"
```
Runs: full panel + test_senescence_difference for each cell type

## Inference States

Every tool result is classified:

| State | ID | User sees |
|-------|-----|-----------|
| DESCRIPTIVE_ONLY | A | Medians/ranks, no p-values |
| LOW_POWER | B | Numeric trend, no statistical conclusion |
| NOT_SIGNIFICANT | C | "Not statistically significant" |
| SIGNIFICANT_INFERENTIAL | D | Cautious significance statement |
| BLOCKED | E | Error message |
