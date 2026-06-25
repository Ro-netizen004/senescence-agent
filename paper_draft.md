# Senescence Agent: A Governed AI Agent for Single-Cell Senescence Analysis

**Draft — not for submission**

---

## Abstract

We present Senescence Agent, a conversational AI system for governed analysis of cellular senescence in single-cell RNA-seq data. Unlike general-purpose LLM tools that narrate quantitative results directly, our agent enforces a formal inference state machine that constrains the claims permitted from each analysis type. The LLM serves only as a query router; all statistical computation, inference state assignment, and user-facing text are produced deterministically. We validate the system on GSE226225 (experimentally induced human senescence, 55,317 cells) and demonstrate the agent on Tabula Muris Senis mouse aging data across multiple tissues. Our results show that SenMayo scoring achieves high precision (0.942) at single-cell level but moderate AUROC (0.563), motivating the governed inference design: the agent structurally prevents overclaiming by labeling cell-level outputs as descriptive only.

---

## 1. Introduction

Single-cell RNA sequencing (scRNA-seq) has transformed the study of cellular senescence, enabling identification of senescent cell populations in aging tissues at transcriptomic resolution. However, statistical analysis of scRNA-seq data carries substantial pitfalls — most critically, pseudoreplication (treating individual cells as independent biological replicates) and LLM overclaiming (AI systems asserting statistical conclusions unsupported by the data).

Existing AI tools for scRNA-seq analysis either wrap bioinformatics tools with LLM narration (BioChatter; Lobentanzer et al. 2024) or rely on general-purpose language models that hallucinate quantitative results. Neither approach provides formal guarantees on the validity of statistical claims.

We introduce Senescence Agent, a system that addresses this gap through three architectural contributions:

1. **Inference state machine** — a formal five-state system (DESCRIPTIVE_ONLY, LOW_POWER, NOT_SIGNIFICANT, SIGNIFICANT_INFERENTIAL, BLOCKED) that assigns each tool result a permitted interpretation level based on statistical evidence quality
2. **Deterministic renderer** — all user-facing text is generated from structured schemas, never from LLM prose, ensuring reproducibility
3. **Pseudoreplication guard** — statistical tests operate on per-sample (biological replicate) medians, not individual cells

---

## 2. Methods

### 2.1 System Architecture

The agent accepts natural language queries and `.h5ad` dataset files. Query routing proceeds through three layers:

**Layer 1 — Intent router (deterministic):** Pure keyword matching routes ~80% of common queries to named workflow templates without LLM involvement. Handles senescence scoring, age comparison, differential expression, UMAP, and statistical testing.

**Layer 2 — Named workflows:** Ordered tool sequences execute deterministically. The panel workflow runs: `find_senescence_markers → senescence_score → generate_umap → get_cluster_annotations → compare_across_age`.

**Layer 3 — Gemini tool selection (LLM):** Unrecognized queries fall through to Gemini 2.5 Flash (temperature=0) for tool selection only. Tool results never pass through the LLM for narration.

### 2.2 Inference State Machine

Every tool result is tagged with an inference state before rendering:

| State | Condition | Permitted Claims |
|---|---|---|
| A — DESCRIPTIVE_ONLY | Exploratory tools (score, UMAP, markers) | Numeric facts only |
| B — LOW_POWER | <3 samples/group or <20 cells/group | Trends only, no conclusion |
| C — NOT_SIGNIFICANT | p ≥ 0.05 with adequate power | No significance claim |
| D — SIGNIFICANT_INFERENTIAL | p < 0.05 with adequate power | Statistical association |
| E — BLOCKED | Tool error | Error message only |

The state is assigned from tool output facts (sample counts, p-values, cell counts) — not from LLM judgment.

### 2.3 Statistical Methods

**Senescence scoring:** SenMayo 125-gene signature (Saul et al. 2022) scored per cell using `sc.tl.score_genes` on log-normalized expression (`use_raw=False`).

**Age comparison:** Mann-Whitney U test on per-sample median senescence scores. Statistical unit: biological replicate (mouse/donor), not individual cell.

**Differential expression:** DESeq2 pseudobulk on raw counts in `adata.layers["counts"]`, aggregated per sample per cell type.

### 2.4 Dataset Profile Inference

At pipeline initialization, the agent infers dataset-specific column names for age, cell type, and sample ID from a ranked candidate list. Age format (months, integer years, categorical labels) is detected automatically. This enables the agent to operate on non-TMS datasets without hardcoded assumptions.

### 2.5 Normalization Detection

Pre-processed datasets (where `adata.raw` is present) are detected automatically. Normalization is skipped and senescence scoring uses `adata.X` directly. Raw counts for DESeq2 are taken from `adata.raw.X`. This prevents double-normalization artifacts that would inflate senescence scores by orders of magnitude.

---

## 3. Validation

### 3.1 GSE226225 — Experimentally Induced Human Senescence

**Dataset:** WI-38 human fibroblasts, 55,317 cells, 33,207 genes. Conditions: CTRL (proliferating), RS (replicative senescence), IR (irradiation-induced), ETO (etoposide-induced, multiple timepoints). Ground-truth labels assigned from experimental design: CTRL and ETO day-0 = non-senescent; RS, IR, ETO day-1+ = senescent (43,280 senescent / 12,037 non-senescent).

**SenMayo coverage:** 122/125 genes detected (98.4%), confirming the signature is well-represented in WI-38 fibroblasts.

**Threshold justification:** We report precision/sensitivity/F1 at the top-25% score threshold as a simple, pre-specified exploratory cutoff. This threshold was not optimized post-hoc; AUROC and AUPRC are reported as primary threshold-independent metrics.

**Metrics:**

| Metric | Value | Notes |
|---|---|---|
| AUROC | 0.563 | Threshold-independent ranking |
| AUPRC | 0.861 | Inflated by class imbalance (78% senescent) |
| Precision (top 25%) | 0.942 | 94.2% of high-scoring cells are truly senescent |
| Sensitivity (top 25%) | 0.301 | Signature captures 30% of all senescent cells |
| F1 (top 25%) | 0.456 | Harmonic mean of precision and sensitivity |

**Interpretation of AUROC:** The moderate AUROC (0.563) reflects a known property of multi-gene population-level signatures applied at single-cell resolution: SenMayo was designed to identify senescent populations, not to rank individual cells. Gene dropout, heterogeneous induction across senescence types (RS, IR, ETO), and the continuous spectrum of senescence states all reduce single-cell discriminability. The high precision (0.942) shows the signature is informative in the high-score regime but does not uniformly separate all senescent cells from non-senescent cells across the full score range.

**AUPRC caveat:** AUPRC of 0.861 is partially inflated by severe class imbalance (78% senescent cells). A random classifier would achieve AUPRC ≈ 0.78 on this dataset. The adjusted improvement over baseline is modest.

**Comparison to single-gene baselines:**

| Method | AUROC | Sensitivity | Precision | F1 |
|---|---|---|---|---|
| CDKN2A (p16) only | 0.506 | 0.484 | 0.757 | 0.590 |
| MKI67 absence | 0.797 | 0.947 | 0.904 | 0.925 |
| SenMayo (ours) | 0.563 | 0.301 | 0.942 | 0.456 |

MKI67 absence achieves higher AUROC (0.797) because cell-cycle arrest is a cleaner binary signal in a single-cell-type dataset where all cells are either proliferating or arrested. SenMayo's strength — a multi-pathway SASP signature — is more appropriate for heterogeneous tissues where MKI67 alone conflates senescence with quiescence and differentiation. SenMayo's superior precision (0.942 vs 0.904) supports its use as a high-specificity filter in heterogeneous tissue contexts.

**Governed inference implication:** Because SenMayo scores are informative at population level but insufficient for single-cell binary classification, the agent structurally assigns `DESCRIPTIVE_ONLY` state to all cell-level score outputs. The agent cannot make senescence classification claims from these scores regardless of how the query is phrased.

### 3.2 Descriptive Reproducibility Across TMS Tissues

To assess whether the agent's analysis pipeline executes correctly on diverse tissue contexts, we ran the standard senescence workflow on five Tabula Muris Senis (TMS) FACS processed tissues: kidney, liver, spleen, aorta, and limb muscle (Tabula Muris Consortium 2020). These five tissues were selected based on local data availability and biological diversity. The goal of this section is reproducibility of workflow execution and coverage — not cross-tissue ranking of senescence burden, which would require matched protocols and cell-type-specific analysis.

All five datasets used TMS processed official annotations with `adata.raw` present. The agent's normalization detection correctly identified all five as pre-processed and skipped double-normalization in every case.

**Workflow completion and SenMayo coverage:**

| Tissue | Cells | Workflow Complete | Coverage % | Genes Used | Score Range |
|--------|-------|-----------------|------------|------------|-------------|
| Kidney | 1,833 | Yes | 90.3 | 112/124 | −0.14 to 0.93 |
| Liver | 2,859 | Yes | 90.3 | 112/124 | −0.13 to 0.60 |
| Spleen | 3,834 | Yes | 90.3 | 112/124 | −0.25 to 0.96 |
| Aorta | 906 | Yes | 90.3 | 112/124 | −0.12 to 0.60 |
| Limb Muscle | 3,855 | Yes | 90.3 | 112/124 | −0.18 to 0.90 |

The standard pipeline completed without error on all five tissues. SenMayo coverage was identical across tissues (90.3%), confirming the mouse ortholog set is stably expressed across tissue types at this sequencing depth. Scores are reported as within-dataset values and are **not directly comparable across tissues** due to differences in cell-type composition and sequencing depth.

**Global age summary (descriptive only — see caveat below):**

| Tissue | Youngest | Oldest | Young Median | Old Median |
|--------|----------|--------|--------------|------------|
| Kidney | 3m | 24m | 0.0551 | 0.0355 |
| Liver | 3m | 24m | 0.0525 | 0.0633 |
| Spleen | 3m | 24m | −0.0015 | −0.0095 |
| Aorta | 3m | 24m | 0.0702 | 0.0603 |
| Limb Muscle | 3m | 24m | 0.1406 | 0.1199 |

**Composition confound caveat:** Global age medians compare all cells in a tissue across age groups. Age-related shifts in cell-type composition (e.g., fewer mesangial cells in old kidney) can drive the global score in either direction even if per-cell senescence is unchanged. These values should be read as a summary of the agent's output, not as evidence of tissue-level senescence trends. Cell-type-specific analysis — available through the agent's `compare_across_age` tool with a `cell_type` argument — is required before any directional biological claim can be made.

**Highest-scoring cell types (within-tissue, by per-cell-type median score):**

| Tissue | Highest-Scoring Cell Type | Notes |
|--------|--------------------------|-------|
| Kidney | mesangial cell | Known to accumulate oxidative damage with age |
| Liver | Kupffer cell | Liver-resident macrophages, established SASP producers |
| Spleen | proerythroblast | Erythroid precursors; senescence role less established |
| Aorta | professional antigen presenting cell | Vascular immune cells; context-dependent |
| Limb Muscle | mesenchymal stem cell | Muscle stem cell senescence implicated in sarcopenia |

These are the cell types with highest per-cell-type median SenMayo score within each tissue. They are presented as descriptive observations to support cell-type-specific follow-up, not as ranked conclusions about which tissue is most senescent.

**Inference state consistency:** All five tissues returned `DESCRIPTIVE_ONLY` for scoring and age comparison outputs, as expected. No tissue had sufficient per-sample replication (TMS: n ≈ 4 mice per age group) to pass the LOW_POWER threshold for statistical testing. This is the correct behavior: the agent self-reports insufficient power rather than proceeding to test.

---

## 4. Discussion

### 4.1 Why Governed Inference

The moderate AUROC on GSE226225 illustrates a broader challenge: transcriptomic senescence signatures are population-level tools being applied at single-cell resolution. Gene dropout, heterogeneous induction across senescence types, and the continuous spectrum of senescence states all reduce single-cell discriminability. An ungoverned AI tool presented with these scores would nonetheless generate confident-sounding biological conclusions. The inference state machine encodes the limitation structurally — the agent cannot claim more than the statistics support regardless of query phrasing.

### 4.2 Pseudoreplication

A fundamental error in scRNA-seq statistics is treating individual cells as independent observations. With thousands of cells per sample, per-cell statistics achieve extreme significance regardless of biological effect size. Our agent prevents this by routing all comparative tests through per-sample aggregation. Statistical unit is always the biological replicate.

### 4.3 Limitations

- **Single signature:** The agent relies solely on SenMayo. p16/p21 expression, CellAge signatures, and SA-β-gal proxies are not incorporated.
- **Transcriptomic only:** Orthogonal validation methods (protein-level immunostaining, functional assays) are not accessible from scRNA-seq data alone.
- **Low power on small cohorts:** TMS has 4 mice per age group — the minimum for pseudobulk analysis. Most age comparisons return LOW_POWER state.
- **Score comparability:** SenMayo scores are relative within a dataset and should not be directly compared across datasets with different protocols.

---

## 5. Conclusion

Senescence Agent demonstrates that formal inference state machines can constrain LLM overclaiming in scientific AI agents. The key insight is architectural: rather than instructing the LLM not to overclaim (which fails under adversarial prompting), we make overclaiming structurally impossible by separating statistical computation, state assignment, and text rendering into deterministic layers. The LLM's role is reduced to query routing — the task where language understanding genuinely adds value.

---

## References

- Saul D, et al. (2022). A new gene set identifies senescent cells and predicts senescence-associated pathways across tissues. *Nature Communications*.
- Tabula Muris Consortium (2020). A single-cell transcriptomic atlas characterizes ageing tissues in the mouse. *Nature*.
- Lobentanzer S, et al. (2024). BioChatter: modern biomedical AI. *Nature Methods*.
- Crowell HL, et al. (2020). muscat detects subpopulation-specific state transitions from multi-sample multi-condition single-cell transcriptomics data. *Nature Communications*.

---

*Draft generated: 2026-06-25. Cross-tissue validation and ablation study pending.*
