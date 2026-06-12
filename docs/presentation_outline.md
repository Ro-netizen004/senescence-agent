# Senescence Agent -- Final Presentation Outline

**Event:** TASH 2026 Hackathon
**Date:** June 29, 2026
**Team:** Aviral (FastAPI Backend, Research, Presentation) & Rodela (Agent, Frontend, Integration)
**Time limit:** ~6 minutes total

---

## Slide 1: Title Slide

- **Title:** Senescence Agent
- **Subtitle:** An LLM-Powered Autonomous Agent for Single-Cell Aging Research
- **Team:**
  - Aviral Gupta -- FastAPI Backend, Research, Presentation
  - Rodela -- Agent Architecture, Frontend, Integration
- **Mentor:** Fei He
- **USF / TASH 2026**

---

## Slide 2: The Problem (Aviral presents, 30 sec)

**Layout:** Split screen

**Left side:** 20 lines of Python code (Scanpy pipeline: load, QC, normalize, cluster, score_genes, groupby, plot)

**Right side:** One chat message: *"Find senescent cells in this aged mouse kidney dataset."*

**Key points:**
- scRNA-seq analysis requires Python/R expertise
- A bioinformatician costs $112K-$180K/year (BLS/Glassdoor 2024-2026)
- Most aging biology labs cannot afford dedicated computational support
- Our tool: same result, one sentence, zero programming

**Opening line:** "Biologists studying aging rely on specialized programming expertise most labs cannot afford."

---

## Slide 3: Why Senescence? (Aviral presents, 15 sec)

- One of the most well-funded areas in aging research
- Calico, Altos Labs, Unity Biotechnology -- billions in investment
- No existing LLM agent specializes in senescence detection
- Our gap: domain-specific tools for the most active area of aging biology

---

## Slide 4: Live Demo (Rodela drives, Aviral narrates, 3 min)

**Demo flow:**
1. Upload TMS kidney .h5ad (species: mouse)
2. Type: "Run the full senescence analysis"
3. Show UMAP + cluster rankings + age comparison
4. Type: "What is the p-value for senescence in T cells, 3m vs 24m?"
5. Show inference state (LOW_POWER or SIGNIFICANT)
6. Click "Download Report"

**Backup:** Pre-recorded demo video open in another tab

---

## Slide 5: Architecture (Aviral presents, 45 sec)

**Diagram:**
```
User --> React Frontend --> FastAPI Backend --> Gemini (tool routing ONLY)
                                                    |
                                          Scanpy Tools (facts-only JSON)
                                                    |
                                          Inference State Machine (A-E)
                                                    |
                                          Deterministic Renderer --> Response
```

**Key points:**
- LLM picks tools, never writes biology
- Scanpy runs real analysis on real data
- Inference state machine prevents overclaiming (A: descriptive only ... D: significant)
- Deterministic renderer -- no LLM prose in results
- All tool calls logged for reproducibility

---

## Slide 6: Senescence Marker Genes (Aviral presents, 20 sec)

**Table of 10 key markers:**

| Gene | Role | Signal |
|------|------|--------|
| CDKN1A (p21) | Cell cycle arrest | High = senescent |
| CDKN2A (p16) | Tumor suppressor, strongest single marker | High = senescent |
| IL6, IL8 | SASP inflammatory cytokines | Co-elevated |
| LMNB1 | Nuclear lamina | Lost in senescent |
| MKI67 | Proliferation marker | Absent = growth arrested |
| TP53 | DNA damage response | Elevated after damage |
| SERPINE1, GLB1, HMGA1 | SASP, lysosomal, chromatin | Classic markers |

**Key point:** "No single marker is sufficient. That's why we use the full SenMayo 125-gene signature."

---

## Slide 7: Novelty -- What Makes Us Different (Aviral presents, 30 sec)

| Feature | CellAgent | CompBioAgent | ELISA | Ours |
|---------|-----------|--------------|-------|------|
| Senescence scoring | No | No | No | SenMayo 125-gene |
| Mouse/human gene mapping | No | No | No | Automatic |
| Age-stratified analysis | No | No | No | Yes |
| Inference state machine | No | No | No | A-E system |
| Deterministic output | No | No | No | Template-rendered |
| Pseudobulk statistics | No | No | No | Mann-Whitney + DESeq2 |

---

## Slide 8: Validation -- GSE226225 (Aviral presents, 30 sec)

**Layout:** Side-by-side UMAP

- Left: Published senescence labels from GSE226225
- Right: Our SenMayo scoring predictions

**Result:** "Our SenMayo scoring identified [X]% of labeled senescent cells on a held-out dataset with known labels."

**Key message:** "This isn't a demo -- it's a scientific result."

---

## Slide 9: Comparison Table (Aviral presents, 20 sec)

| Method | Sensitivity | Precision | F1 |
|--------|-------------|-----------|-----|
| CDKN2A (p16) only | [X]% | [Y]% | [Z]% |
| MKI67 absence | [X]% | [Y]% | [Z]% |
| SenMayo (ours) | [X]% | [Y]% | [Z]% |

**Key message:** "Single markers miss entire categories of senescent cells. The full signature captures the multi-dimensional phenotype."

---

## Slide 10: Limitations & Future Work (Aviral presents, 30 sec)

**Limitations:**
- RNA-seq only (senescence is multi-modal)
- Primarily tested on mouse data (Tabula Muris Senis)
- SenMayo coverage varies by tissue (20-80%)

**Future work:**
- Human clinical datasets (GTEx, Human Cell Atlas)
- ATAC-seq integration for epigenetic markers
- Custom gene signatures (user-defined panels)
- Spatial transcriptomics

---

## Slide 11: Results / User Quote (Aviral presents, 15 sec)

**Large pull-quote box:**

> "I would actually use this for my aging dataset analysis."
>
> -- Graduate Student, Aging Biology Lab

*(Quote captured during Week 6 user test)*

---

## Slide 12: Team & Acknowledgments

- **Aviral Gupta** -- FastAPI Backend, Research Narrative, Presentation
- **Rodela** -- Agent Architecture, Frontend, Integration
- **Mentor:** Fei He
- **Built with:** Scanpy, FastAPI, Google Gemini, React, SenMayo signature
- **Datasets:** Tabula Muris Senis, GSE226225

---

## Slide 13: Q&A

"Questions?"

*(See docs/qa_answers.md for prepared answers)*
