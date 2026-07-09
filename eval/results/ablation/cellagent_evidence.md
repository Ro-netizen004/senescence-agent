# CellAgent "Wild Agent" Evidence — Autonomous Pseudoreplication on a Null

**Purpose:** proof that an independent, published single-cell agent (CellAgent),
driven by the same LLM as our agent (Gemini), autonomously plans per-cell
differential expression on a constructed-null dataset — pseudoreplication with no
statistical-unit check — where the true number of DE genes is zero.

## Setup (for reproducibility)

| | |
|---|---|
| Agent | CellAgent (Liu Shiqiang). Repo: https://github.com/lsq2wal/CellAgent (mirror of liu-shiqiang/CellAgent), arXiv:2407.09811 |
| LLM | Google Gemini 2.5 Flash (`GoogleGenerativeAI`, temperature 0) — same model as our agent |
| Date run | 2026-07-05 (Colab) |
| Input | `cellagent_null.h5ad` — 105 cells, one cell type (fenestrated cell), 4 real 24-month male mice randomly split into `groupA` (55 cells) / `groupB` (50 cells). Same age + sex → **genuine null; truth = 0 DE genes**. `sample_id` (mouse) column present in `obs`. |
| Task prompt | "Identify the genes that are differentially expressed between groupA and groupB. Report how many genes are statistically significant." |

## The evidence: CellAgent's autonomously-generated plan

CellAgent's Planner produced an 8-step plan. The decisive step:

> **Step 5 (verbatim, translated):** "Differential expression (DEG) analysis.
> Compare gene expression between `groupA` and `groupB`.
> a. **Run `scanpy.tl.rank_genes_groups`** with `groupby='group'`,
> `groups=['groupA']`, `reference='groupB'`.
> b. Choose a statistical test, e.g. 'wilcoxon' or 't-test'."

Original (Chinese):
> 步骤 5：差异表达基因 (DEG) 分析。... a. 运行`scanpy.tl.rank_genes_groups`：调用此函数，
> 指定`groupby='group'`，`groups=['groupA']`和`reference='groupB'`... b. 选择统计检验方法，
> 例如'wilcoxon'... 或't-test'...

**This is per-cell differential expression.** `rank_genes_groups` on `groupby='group'`
tests individual cells; there is no aggregation to the biological replicate
(`sample_id`). The plan never mentions pseudobulk, biological replicates,
`sample_id`, mouse, or donor.

Corroborating signals in the same plan:
- **Step 1 (translated):** "...check the cell-count distribution of the two groups
  to ensure there are **enough cells** for statistical analysis." → reasons about
  *cell* count as the statistical unit (the pseudoreplication mindset).
- **Step 6:** relies on scanpy's built-in per-cell BH-FDR as valid.
- **Step 7:** filters significant genes at `p_adj < 0.05` from the per-cell test.

## Generated code (Executor)

The Executor's QC code confirms it operated purely at the cell level and never
used `sample_id`:

```python
adata = sc.read_h5ad("cellagent_null.h5ad")
adata.X = adata.layers['counts'].copy()
adata.var['mt'] = adata.var_names.str.startswith('MT-')
sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], ...)
sc.pp.filter_cells(adata, min_genes=200)
sc.pp.filter_cells(adata, max_genes=2500)
sc.pp.filter_cells(adata, min_counts=500)
sc.pp.filter_cells(adata, max_counts=10000)
adata = adata[adata.obs['pct_counts_mt'] < 5, :].copy()
sc.pp.filter_genes(adata, min_cells=3)
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
```

## Execution: CellAgent reported 36 false genes

**Standard task (autonomous QC):** CellAgent's own generic droplet QC
(`max_genes=2500`, `max_counts=10000`) removed all Smart-seq2 cells (which have
thousands of genes / high counts), emptying the matrix (`ValueError: Found array
with 0 sample(s)` at `log1p`). This is a separate robustness weakness (wrong QC
defaults for FACS data), not the statistical-unit finding.

**QC-bypass task (told the data were pre-processed):** CellAgent skipped QC and
executed its chosen per-cell test. Its generated Step-1 code ran
`sc.tl.rank_genes_groups(adata_subset, 'group', method='wilcoxon')` and printed:

```
WARNING: It seems you use rank_genes_groups on the raw count data...
36
```

So CellAgent **executed per-cell differential expression and reported 36
significant genes at FDR < 0.05** on the null (truth = 0) — 36 false discoveries.
(It also ran on raw counts, a further data-state error; Wilcoxon is rank-based so
the p-values are unaffected.) Saved: `analysis_20260705_083332.ipynb`.

## The quantified failure

- **CellAgent, executed:** 36 false-positive genes (FDR < 0.05; all genes, no
  detection filter). Truth = 0.
- **Same per-cell method, our harness (detection-filtered):** mean 221 false
  genes across splits of this cell type (Table 1, `null_Kidney_fenestrated_cell.json`);
  the exact seed-0 split yields 101.

Either way, per-cell DE on a null yields tens-to-hundreds of false discoveries.
Our admissibility gate refuses the identical input.

## Claim supported

> A published single-cell agent (CellAgent), using the same LLM as our system,
> autonomously selects per-cell differential expression with no biological-replicate
> aggregation — pseudoreplication — on data whose true DE-gene count is zero. The
> failure is therefore not an artifact of our ablation; it occurs in a deployed
> agent. Our governance refuses the same analysis.

## Raw artifacts to keep with this record

- The full CellAgent console log (plan + Executor attempts) — saved as
  `cellagent_run_log.txt` (paste from Colab).
- CellAgent's generated notebooks: `examples/notebooks/analysis*.ipynb`
  (download from Colab: `files.download('examples/notebooks/analysis.ipynb')`).
