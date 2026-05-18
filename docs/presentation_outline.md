# Senescence Agent: Presentation Outline

This document provides a slide-by-slide outline for your upcoming presentation.

## Slide 1: Title Slide
- **Project Name:** Senescence Agent
- **Subtitle:** An LLM-powered autonomous agent for single-cell aging research.
- **Team Roles:** 
  - Aviral (Agent Architecture, Frontend, API Integration)
  - Rodela (Agent Logic, Prompt Engineering)
  - [Other teammates, if any]

## Slide 2: The Problem
- **Bottleneck:** Analyzing single-cell RNA-seq (scRNA-seq) data requires deep programming expertise (Python/R).
- **Aging Biology Gap:** Current AI tools (like CellAgent or CompBioAgent) are general-purpose. There is no automated, natural-language interface tailored specifically for identifying and scoring cellular senescence.
- **Impact:** Slows down the discovery of senescent cell populations in tissue models.

## Slide 3: Our Solution
- **What it is:** A zero-code, conversational AI web application.
- **How it works:** Users upload an `.h5ad` file and ask questions in plain English. The agent converts this into Python commands, orchestrating the `Scanpy` library to perform QC, clustering, and dimensional reduction (UMAP).
- **The "Secret Sauce":** Built-in utilization of the **SenMayo signature** to automatically map cross-species gene names and calculate senescence burden per cell cluster.

## Slide 4: What We Have Done So Far (Week 1 Progress)
- **Verified Core Literature:** Reviewed existing benchmarks like CellAgent, CompBioAgent, and ELISA.
- **Backend Architecture Setup:**
  - Configured a Python virtual environment with all core bioinformatics and AI dependencies (`scanpy`, `fastapi`, `anthropic`).
  - Built a robust FastAPI server exposing `/upload` and `/chat` endpoints with CORS and Session Management.
- **Frontend Scaffolding:** Initialized the React + TypeScript + Vite workspace with TailwindCSS.
- **API Contract Locked:** Established the exact JSON request/response schema with the agent team (Rodela).

## Slide 5: Weekly Deliverables & Project Plan
- **Week 1 (Current): Foundation**
  - Scaffold frontend/backend.
  - Establish API contract and build mock endpoints.
  - Implement basic Scanpy utility functions (QC, UMAP, Gene Nomenclature mapping).
- **Week 2: Core Agent Logic**
  - Rodela integrates the LLM (Ollama/Anthropic) to parse user intent.
  - Agent successfully calls the Scanpy python tools based on chat prompts.
- **Week 3: Frontend Integration**
  - Connect the React chat interface to the `/chat` endpoint.
  - Render UMAP PNGs and agent text responses dynamically in the UI.
- **Week 4: Polish & Hackathon Demo**
  - Test the agent with real PBMC/aging datasets.
  - Final bug fixes, styling improvements, and presentation prep for TASH 2026.

## Slide 6: Architecture Overview (Optional)
- Briefly explain the hybrid LLM approach: **Ollama (Llama 3.1 8B)** for local prototyping and **Anthropic Claude** for robust reasoning.
- Mention the split between React (UI) <-> FastAPI (Orchestrator) <-> Scanpy (Engine).
