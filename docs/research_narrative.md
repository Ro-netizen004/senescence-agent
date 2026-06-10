# Senescence Agent -- Research Narrative

## 1. Introduction

Cellular senescence -- the irreversible arrest of cell division -- plays a pivotal role in aging, tissue remodeling, and age-related pathologies including cancer, fibrosis, and neurodegeneration. Senescent cells accumulate with age, secrete a cocktail of inflammatory factors known as the senescence-associated secretory phenotype (SASP), and drive chronic tissue dysfunction. Identifying these cells within heterogeneous tissues is therefore a central goal of modern aging research.

Single-cell RNA sequencing (scRNA-seq) gives researchers unprecedented resolution to profile individual cells within a tissue, enabling the identification and characterization of senescent populations that would be invisible in bulk assays. However, analyzing scRNA-seq data requires deep expertise in Python or R programming, specialized bioinformatics pipelines, and statistical reasoning about pseudobulk inference. This creates a critical bottleneck: the biologists who understand senescence biology often lack the computational skills to analyze their own data, while bioinformaticians may lack the domain knowledge to ask the right biological questions.

**Senescence-Agent** bridges this gap by providing an LLM-powered autonomous agent that translates plain-English questions into reproducible Scanpy analysis pipelines, specialized for senescence detection.

## 2. Background

### 2.1 Single-Cell RNA Sequencing

Single-cell RNA sequencing (scRNA-seq) measures the transcriptome of individual cells, producing expression matrices with thousands of cells and tens of thousands of genes. Standard analysis pipelines include:

- **Quality control (QC):** Filtering cells by gene count, mitochondrial fraction, and doublet detection
- **Normalization:** Library-size correction and log-transformation to make expression values comparable across cells
- **Dimensionality reduction:** PCA followed by UMAP for 2D visualization
- **Clustering:** Community detection algorithms (e.g., Leiden) to group cells with similar transcriptional profiles
- **Differential expression:** Identifying genes that change between conditions, age groups, or cell states

The standard tool for this pipeline is **Scanpy** (Wolf et al., 2018), a Python library that handles datasets with millions of cells. A typical analysis requires 50-200 lines of Python code and familiarity with AnnData, the underlying data structure.

### 2.2 Cellular Senescence

Cellular senescence is defined by several hallmarks:

| Hallmark | Key Genes | Detection Method |
|----------|-----------|-----------------|
| Cell cycle arrest | CDKN1A (p21), CDKN2A (p16/INK4a) | Expression level |
| SASP secretion | IL6, IL8/CXCL8, SERPINE1 (PAI-1) | Co-expression pattern |
| Loss of proliferation | MKI67 (Ki-67) | Absence of expression |
| Nuclear envelope changes | LMNB1 (Lamin B1) | Loss of expression |
| DNA damage response | TP53 | Elevated expression |
| Lysosomal changes | GLB1 (SA-beta-Gal) | Classic enzymatic marker |
| Chromatin remodeling | HMGA1 | Increased in replicative senescence |

No single marker is sufficient. CDKN2A (p16) is the most commonly used, but it is not expressed in all senescent cell types. IL6 and IL8 are part of the SASP but are also elevated in inflammation. MKI67 absence indicates growth arrest but does not distinguish senescence from quiescence.

This is why **multi-gene signatures** are essential. The SenMayo gene set (Saul et al., 2022, Nature Communications) provides 125 validated senescence-associated genes that collectively identify senescent cells across tissues and species with higher specificity than any single marker.

### 2.3 Why Current Tools Require Programming Expertise

A researcher who wants to answer "Which cell types become senescent with age in my kidney dataset?" must currently:

1. Load the `.h5ad` file in Python (`scanpy.read_h5ad`)
2. Run QC filtering (3-5 lines of code)
3. Normalize and cluster (5-8 lines)
4. Score cells against SenMayo genes (`sc.tl.score_genes`)
5. Handle mouse vs. human gene name conversion (10+ lines)
6. Group by cell type and age, compute per-sample medians
7. Run statistical tests with proper pseudobulk aggregation
8. Generate plots and interpret results

This requires knowledge of Python, Scanpy, AnnData, pandas, scipy, and correct statistical methodology (pseudobulk, not per-cell tests). A bioinformatician with this skillset earns a median salary of $112,590/year (BLS, 2024) to $180,394/year (Glassdoor, 2026), and many academic labs cannot afford dedicated computational support.

**Our tool reduces this to one sentence:** "Find senescent cells in this aged mouse kidney dataset."

### 2.4 The SenMayo Gene Signature

The SenMayo gene set (Saul et al., 2022) is a 125-gene panel validated across:

- Multiple tissues (bone, bone marrow, liver, kidney, brain)
- Multiple species (human and mouse, with validated orthologs)
- Multiple senescence inducers (replicative, oncogene-induced, therapy-induced)

Our agent uses SenMayo as its primary scoring mechanism. Each cell receives a score based on the average expression of available SenMayo genes (via `sc.tl.score_genes`). Higher scores indicate a stronger senescence-associated transcriptional phenotype.

### 2.5 Mouse vs. Human Gene Name Mapping

SenMayo is defined using human gene symbols (CDKN1A, IL6 -- uppercase). Mouse datasets such as Tabula Muris Senis use title-case symbols (Cdkn1a, Il6). Some conversions are non-trivial:

- TP53 (human) maps to **Trp53** (mouse), not Tp53
- IL8/CXCL8 (human) has no direct mouse ortholog; **Cxcl5** or **Cxcl15** serve as proxies

Our agent handles this automatically via a species parameter. The `gene_utils.py` module uses the MyGene API for accurate conversion, with a hardcoded fallback dictionary for critical genes like TP53/Trp53.

## 3. Prior Art and the Gap We Fill

### 3.1 CellAgent (Xiao et al., 2024)

CellAgent is an LLM-driven multi-agent framework for automated single-cell data analysis. It uses hierarchical task planning with planner, executor, and evaluator agents.

**What it does well:** General-purpose scRNA-seq automation -- QC, clustering, annotation.

**What it does NOT do:** No senescence-specific tools, no SenMayo scoring, no age-comparison analysis, no species-aware gene mapping for aging markers.

### 3.2 CompBioAgent (bioRxiv, 2025)

CompBioAgent is an LLM-powered web application that interfaces with CellDepot for natural-language exploration of scRNA-seq data. It generates visualizations (violin plots, UMAPs, heatmaps) from conversational queries.

**What it does well:** Database-backed exploration, broad visualization capabilities.

**What it does NOT do:** No senescence scoring, no custom gene signature support, no statistical testing for age-related changes, no report generation.

### 3.3 ELISA (Coser et al., 2026)

ELISA (Embedding-Linked Interactive Single-cell Agent) uses scGPT expression embeddings with BioBERT-based semantic retrieval for interactive single-cell discovery. It includes pathway scoring and ligand-receptor interaction prediction.

**What it does well:** Embedding-based discovery, mechanistic hypothesis generation.

**What it does NOT do:** No senescence-specific workflows, no SenMayo integration, no age-stratified statistical analysis, no local/private deployment.

### 3.4 Our Contribution

Senescence-Agent is the first LLM agent specialized for cellular senescence detection in scRNA-seq data. Our unique contributions:

1. **Domain specialization:** Pre-loaded SenMayo 125-gene signature with automatic species mapping
2. **Statistical rigor:** Sample-level (pseudobulk) inference via Mann-Whitney U and DESeq2, not naive per-cell tests
3. **Inference state machine:** System-enforced guardrails (A-E states) that prevent the LLM from hallucinating statistical conclusions
4. **Deterministic output:** User-facing text is generated by a template renderer from tool facts, not free-form LLM prose
5. **Reproducible reports:** Every tool call is logged with arguments and results; Markdown/PDF reports are generated from this audit trail

## 4. Methodology

### 4.1 Architecture Overview

```
User (browser) --> React Frontend --> FastAPI Backend --> Gemini Agent
                                                              |
                                                   Tool Selection (routing only)
                                                              |
                                              Scanpy Tools (facts-only JSON)
                                                              |
                                              Inference State Machine (A-E)
                                                              |
                                              Deterministic Output Renderer
                                                              |
                                              Structured Response --> Frontend
```

### 4.2 Agent Loop (ReAct Pattern)

The agent follows the ReAct paradigm (Yao et al., 2022): Reason + Act in a loop.

1. User sends a question via `/chat`
2. FastAPI loads the dataset and ensures the preprocessing pipeline has run (QC, normalization, Leiden clustering)
3. The message is routed to Google Gemini with tool schemas
4. Gemini selects which tool(s) to call (it does NOT generate biology)
5. The selected tool executes on real data via Scanpy, returning facts-only JSON
6. The inference state machine assigns a state (A-E) based on statistical power and significance
7. The deterministic renderer converts tool results into user-facing text using templates
8. If Gemini requests another tool, loop back to step 4 (max 3-5 iterations)

### 4.3 SenMayo Scoring Approach

```python
sc.tl.score_genes(adata, gene_list=available_senmayo_genes, score_name="senescence_score")
```

Each cell receives a score equal to the mean expression of SenMayo genes minus the mean expression of a random reference set (Scanpy's default method). This controls for library size and general transcriptional activity.

Scores are then aggregated per cluster, per cell type, and per age group. For statistical comparisons, we use **per-sample medians** (one value per biological replicate), not per-cell values, to avoid pseudoreplication.

### 4.4 Inference State Machine

Every tool result is classified into one of five states:

| State | ID | Meaning | User sees |
|-------|-----|---------|-----------|
| DESCRIPTIVE_ONLY | A | No p-value possible from this tool | Medians and ranks only |
| LOW_POWER | B | Too few samples or cells | Numeric trend, no conclusion |
| NOT_SIGNIFICANT | C | Test ran, p >= 0.05 | "Not statistically significant" |
| SIGNIFICANT_INFERENTIAL | D | Test ran, p < 0.05, adequate power | Cautious significance statement |
| BLOCKED | E | Tool error | Error message only |

This prevents the LLM from claiming statistical significance when the data does not support it.

### 4.5 Species Gene Name Mapping

All tools accept a `species` parameter (`mouse` or `human`). Gene name conversion follows this rule:

```python
# Human: CDKN1A, IL6, TP53 (uppercase)
# Mouse: Cdkn1a, Il6, Trp53 (title case, with special mappings)

if species == "mouse":
    genes = normalize_gene_names(SENMAYO_GENES, species="mouse")
```

The `normalize_gene_names` function uses the MyGene API for accurate ortholog mapping, with a hardcoded fallback dictionary for genes with non-trivial mappings (TP53 -> Trp53, IL8 -> Cxcl15).

## 5. Expected Outcomes

1. **Accessibility:** A non-computational biologist can upload an `.h5ad` file and identify senescent cell populations through conversation
2. **Specialization:** Accurate senescence scoring using the validated SenMayo signature across mouse and human datasets
3. **Reproducibility:** Every analysis step is logged; reports include tool call traces, parameters, and results
4. **Statistical integrity:** The inference state machine prevents overclaiming from underpowered data

## 6. Limitations

- **Transcriptomics only:** Senescence is a multi-modal phenotype. RNA expression alone cannot capture morphological changes (SA-beta-Gal staining) or epigenetic modifications
- **Mouse-focused:** Primary testing on Tabula Muris Senis. Human datasets require further validation
- **SenMayo coverage:** Not all 125 SenMayo genes are expressed in every tissue. Coverage varies from 20-80% depending on the dataset
- **No spatial context:** scRNA-seq loses tissue architecture. Spatial transcriptomics integration is future work

## 7. Future Directions

- **ATAC-seq integration:** Chromatin accessibility data could identify senescence-associated epigenetic changes
- **Human clinical datasets:** Validation on human aging cohorts (e.g., GTEx, Human Cell Atlas)
- **Custom gene signatures:** Allow users to define their own marker gene sets beyond SenMayo
- **Literature retrieval (RAG):** Cross-reference identified markers with published senescence literature
- **Spatial transcriptomics:** Map senescent cells within tissue architecture

## References

1. Saul, D. et al. (2022). A new gene set identifies senescent cells and predicts senescence-associated pathways across tissues. *Nature Communications*, 13, 4827. DOI: 10.1038/s41467-022-32552-1
2. The Tabula Muris Consortium (2020). A single-cell transcriptomic atlas characterizes ageing tissues in the mouse. *Nature*, 583, 590-595. DOI: 10.1038/s41586-020-2496-1
3. Yao, S. et al. (2022). ReAct: Synergizing Reasoning and Acting in Language Models. arXiv:2210.03629
4. Xiao, Y. et al. (2024). CellAgent: An LLM-driven Multi-Agent Framework for Automated Single-cell Data Analysis. arXiv:2407.09811
5. CompBioAgent (2025). An LLM-powered agent for single-cell RNA-seq data exploration. bioRxiv. DOI: 10.1101/2025.03.17.643771
6. Coser, O. et al. (2026). ELISA: An Interpretable Hybrid Generative AI Agent for Expression-Grounded Discovery in Single-Cell Genomics. arXiv:2603.11872
7. Wolf, F.A. et al. (2018). SCANPY: large-scale single-cell gene expression data analysis. *Genome Biology*, 19, 15.
