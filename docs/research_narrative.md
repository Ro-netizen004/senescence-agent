# Senescence Agent: Research Narrative

*(Note: Copy and paste this document into your shared Google Doc for the team.)*

---

## 1. Introduction
Cellular senescence plays a pivotal role in aging, tissue remodeling, and various age-related pathologies. With the advent of single-cell RNA sequencing (scRNA-seq), researchers have gained unprecedented resolution to identify and characterize senescent cells within complex tissues. However, the data analysis bottleneck—requiring deep expertise in programming and bioinformatics—hinders rapid biological discovery. **Senescence-Agent** aims to bridge this gap by introducing an LLM-driven autonomous framework capable of executing specialized single-cell analysis workflows through natural language interactions.

## 2. Related Work
Recent advancements in agentic AI for biology have demonstrated the feasibility of automating transcriptomic analyses:
- **CellAgent**: An LLM-driven multi-agent framework that successfully automates single-cell data analysis through hierarchical task planning and execution.
- **CompBioAgent**: Demonstrated the ability to explore scRNA-seq data and interface with databases like CellDepot using natural language queries.
- **ELISA**: (Embedding-Linked Interactive Single-cell Agent) Showcased how AI can generate mechanistic biological hypotheses by linking expression embeddings with biomedical knowledge retrieval.

While these tools offer generalized transcriptomic capabilities, they lack specialized workflows for aging biology, presenting an opportunity for a targeted senescence analysis tool.

## 3. Methodology
Senescence-Agent is designed with a modern, decoupled architecture:
- **Frontend**: A React/Vite interface providing an interactive chat experience and visual plot rendering.
- **Backend/Integration**: A FastAPI server managing user sessions and multipart file uploads (`.h5ad`).
- **Agentic Engine**: A hybrid LLM system (Ollama for local privacy/speed, Anthropic Claude for complex orchestration) that interprets user requests.
- **Bioinformatics Toolkit**: Core execution relies on `Scanpy` to perform quality control, dimensional reduction (UMAP), and clustering (Leiden).
- **Senescence Scoring**: Custom modules that utilize the *SenMayo* gene signature, implementing cross-species gene nomenclature mapping (e.g., human vs. mouse) to score cellular senescence dynamically.

## 4. Expected Outcomes
By deploying Senescence-Agent at the TASH 2026 hackathon, we aim to demonstrate:
1. **Accessibility**: Enabling non-computational biologists to successfully analyze a PBMC or tissue dataset via conversational AI.
2. **Specialization**: Accurate identification and scoring of senescent clusters using the SenMayo signature.
3. **Reproducibility**: Automatic generation of standardized plots (UMAP) and reproducible analysis trails.

## 5. Future Directions
Subsequent iterations of the agent could integrate spatial transcriptomics, automated report generation, and direct literature retrieval (RAG) to cross-reference identified senescent markers with the latest aging research.
