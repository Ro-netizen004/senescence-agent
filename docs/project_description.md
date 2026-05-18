# Senescence Agent: Project Description

## The Problem
Single-cell RNA sequencing (scRNA-seq) has revolutionized our understanding of cellular heterogeneity, particularly in the context of aging and disease. However, exploring and analyzing this massive volume of transcriptomic data remains a highly technical and labor-intensive process. Biologists and aging researchers often lack the specialized programming skills (Python/R) required to properly conduct quality control, clustering, and specialized scoring. This creates a significant bottleneck in translating raw data into meaningful biological hypotheses, especially for niche fields like cellular senescence.

## The Solution
**Senescence-Agent** is an end-to-end, LLM-powered bioinformatics agent designed to democratize scRNA-seq analysis. By providing a natural language interface, researchers can upload their datasets (`.h5ad`) and interactively query the data without writing a single line of code. Under the hood, the agent orchestrates the industry-standard `Scanpy` library to autonomously execute analytical pipelines—including quality control, normalization, UMAP visualizations, and clustering. The agent acts as an automated bioinformatician, explaining its methodology and delivering interpretable results directly to the user.

## Senescence Focus
While general-purpose single-cell agents (like CompBioAgent or CellAgent) exist, Senescence-Agent is highly specialized for aging research. It comes pre-equipped with the **SenMayo gene signature**—a robust, cross-tissue panel of genes indicative of cellular senescence. The agent can automatically map gene nomenclatures across species (e.g., human `CDKN1A` vs. mouse `Cdkn1a`) and calculate quantitative senescence scores for identified cell clusters, accelerating the discovery of senescent cell burdens in various experimental conditions.

## Architectural Decision: LLM Selection (Anthropic vs. Ollama)
To balance performance, privacy, and cost, the project will adopt a **hybrid LLM architecture**:
- **Ollama (llama3.1:8b)**: Will be used for local development, fast prototyping, and tasks requiring strict data privacy (e.g., handling sensitive, unpublished human datasets locally).
- **Anthropic (Claude API)**: Will serve as the primary production fallback for complex reasoning, tool orchestration, and deep biological interpretations where smaller local models might struggle with context limits or instruction adherence.
