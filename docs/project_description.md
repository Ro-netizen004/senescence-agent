# Senescence Agent: Project Description

## The Problem

Single-cell RNA sequencing (scRNA-seq) has revolutionized our understanding of cellular heterogeneity, particularly in the context of aging and disease. However, analyzing this data remains a highly technical and labor-intensive process. Biologists and aging researchers often lack the specialized programming skills (Python/R) required to conduct quality control, clustering, and specialized scoring. A bioinformatician with these skills earns $112,590/year (BLS median, 2024) to $180,394/year (Glassdoor, 2026), and many academic labs cannot afford dedicated computational support.

This creates a critical bottleneck: the researchers who understand senescence biology cannot analyze their own single-cell data, while bioinformaticians may lack the domain knowledge to ask the right biological questions.

## The Solution

**Senescence-Agent** is an end-to-end, LLM-powered bioinformatics agent that lets researchers upload `.h5ad` datasets and interactively query them in plain English. Under the hood, the agent orchestrates the industry-standard Scanpy library to autonomously execute analytical pipelines -- quality control, normalization, Leiden clustering, UMAP visualization, and senescence-specific scoring.

The key design principle: **Python owns the science; the LLM routes tools only.** User-facing answers are produced by a deterministic template renderer from tool facts, not free-form LLM prose. This ensures reproducibility and prevents hallucinated biology.

## Why Senescence Specifically

Cellular senescence is one of the most well-funded and active areas in aging research. Companies like Calico, Altos Labs, and Unity Biotechnology are investing billions in understanding and targeting senescent cells. Yet no existing LLM agent specializes in senescence detection. CellAgent (Xiao et al., 2024) is general-purpose scRNA-seq. CompBioAgent (2025) focuses on database exploration via CellDepot. ELISA (Coser et al., 2026) uses embedding-based discovery. None provide:

- Pre-loaded SenMayo 125-gene senescence signature with automatic species mapping
- Age-stratified statistical analysis with proper pseudobulk methodology
- An inference state machine that prevents overclaiming from underpowered data
- Deterministic output rendering from tool-generated facts

This gap is our contribution.

## Architecture

```
User (browser) --> React Frontend --> FastAPI Backend --> Google Gemini (tool routing only)
                                                              |
                                                    Scanpy Tools (facts-only JSON)
                                                              |
                                                    Inference State Machine (A-E)
                                                              |
                                                    Deterministic Renderer --> Response
```

- **Frontend:** React + TypeScript + Vite + Tailwind. Upload, chat, plot display, report download.
- **Backend:** FastAPI server managing sessions, file uploads, and agent orchestration.
- **Agent:** Google Gemini selects which Scanpy tool to call. It never generates biology.
- **Tools:** Scanpy-based analysis (QC, clustering, SenMayo scoring, age comparison, DESeq2).
- **Inference State Machine:** Classifies every tool result into states A-E based on statistical power, preventing the LLM from claiming significance when the data doesn't support it.
- **Renderer:** Deterministic templates convert tool JSON into user-facing text. No LLM prose in results.

## Species Gene Name Mapping

SenMayo is a human gene set (CDKN1A, IL6 -- uppercase). Mouse datasets like Tabula Muris Senis use title-case (Cdkn1a, Il6). Some mappings are non-trivial (TP53 -> Trp53, IL8 -> Cxcl15). All tools take a `species` parameter, and the `gene_utils.py` module handles conversion via the MyGene API with hardcoded fallbacks for critical genes.

## Key References

1. Saul et al. (2022). SenMayo gene signature. *Nature Communications* 13:4827.
2. Tabula Muris Consortium (2020). Aging mouse atlas. *Nature* 583:590-595.
3. Xiao et al. (2024). CellAgent. arXiv:2407.09811.
4. CompBioAgent (2025). bioRxiv:2025.03.17.643771.
5. Coser et al. (2026). ELISA. arXiv:2603.11872.
6. Yao et al. (2022). ReAct agent pattern. arXiv:2210.03629.
