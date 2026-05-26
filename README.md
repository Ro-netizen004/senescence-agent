# Senescence Agent

Single-cell RNA-seq analysis for **cellular senescence** and **aging**, driven by natural language. Upload an `.h5ad` dataset, ask questions in chat, and get reproducible Scanpy results with audit-friendly tool logs.

**Design principle:** Python owns the science; Google Gemini routes tools only. User-facing answers after tool runs are produced by a **deterministic renderer**, not free-form LLM prose.

---

## What it does

- Preprocesses data once per upload (QC, normalization, Leiden clustering)
- Scores cells with the **SenMayo** gene signature (mouse/human orthologs)
- Compares senescence across age groups and cell types
- Runs **sample-level** statistical tests (Mann–Whitney on per-mouse medians, not pooled cells)
- Runs **pseudobulk DESeq2** for gene-level aging contrasts
- Generates UMAP and distribution plots served at `/plots`
- Builds Markdown/PDF reports from the **tool execution log** (not chat hallucination)

---

## Architecture

```text
Upload (.h5ad) → FastAPI → run_agent
                              │
                    ensure_pipeline (QC, norm, cluster)
                              │
                    Gemini: tool selection only
                              │
                    Scanpy tools (facts-only JSON)
                              │
                    inference_state (A–E state machine)
                              │
                    output_schema → output_renderer → chat reply
```

### Inference states (system-enforced)

| State | Meaning |
|--------|---------|
| `DESCRIPTIVE_ONLY` | Medians/ranks only; no p-values from this tool |
| `LOW_POWER` | Too few mice/cells; **no statistical conclusion** |
| `NOT_SIGNIFICANT` | Test ran; p ≥ 0.05 — numeric trend only |
| `SIGNIFICANT_INFERENTIAL` | Sample- or gene-level significance allowed (cautious wording) |
| `BLOCKED` | Tool error; no inference |

Key modules:

| Path | Role |
|------|------|
| `backend/agent/agent.py` | Orchestration, tool execution |
| `backend/agent/inference_state.py` | State machine + power gating |
| `backend/agent/output_schema.py` | Strict JSON slots (`interpretation: "not permitted"`) |
| `backend/agent/output_renderer.py` | Template-based user text (no LLM) |
| `backend/tools/` | Scanpy analysis (numbers/metadata only) |

Deep dive: [docs/senescence_agent_architecture.md](docs/senescence_agent_architecture.md) (PDF: `docs/senescence_agent_architecture.pdf`).

Regenerate PDF:

```bash
backend\venv\Scripts\python.exe scripts\generate_architecture_pdf.py
```

---

## Analysis tools (Gemini can invoke)

| Tool | Level | Output |
|------|--------|--------|
| `find_senescence_markers` | Cell | SenMayo gene coverage |
| `senescence_score` | Cell | Per-cell/cluster SenMayo scores + UMAP |
| `generate_umap` | Cell | Cluster UMAP |
| `get_cluster_annotations` | Cell | Cluster → cell type mapping |
| `compare_across_age` | Descriptive | Median scores by age (no p-value) |
| `test_senescence_difference` | Inferential | Mann–Whitney on **per-sample** medians |
| `run_deseq2` | Gene | Pseudobulk DESeq2 (FDR, log2FC) |

For a **score p-value**, use `test_senescence_difference` (e.g. T cell, `3m` vs `24m`).  
For **gene-level** significance, use `run_deseq2` on a specific cell type.

---

## Project structure

```text
senescence-agent/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── agent/               # Agent, pipeline, inference, renderer
│   ├── tools/               # Scanpy analysis
│   ├── data/uploads/        # Persisted .h5ad (gitignored)
│   └── outputs/             # Plots + reports
├── frontend/                # React + TypeScript (Vite)
├── docs/                    # Architecture guide, narratives
├── scripts/                 # e.g. architecture PDF generator
├── .env                     # GEMINI_API_KEY (not committed)
└── README.md
```

---

## Requirements

- Python 3.10+
- Node.js 18+ (frontend)
- `GEMINI_API_KEY` in `.env` at repo root

```env
GEMINI_API_KEY=your_key_here
# optional:
GEMINI_MODEL=gemini-2.5-flash
VITE_API_URL=http://127.0.0.1:8000
```

---

## Local development

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
python main.py
```

Server: `http://127.0.0.1:8000`  
Health: `GET /health`

### Frontend

```bash
cd frontend
npm install
cp .env.example .env           # set VITE_API_URL if needed
npm run dev
```

App: `http://localhost:5173`

---

## API

### `POST /upload`

Multipart: `file` (`.h5ad`), `species` (`mouse` | `human`).

```json
{ "file_id": "uuid", "species": "mouse" }
```

### `POST /chat`

```json
{
  "session_id": "string",
  "message": "What is the p-value for senescence in T cells, 3m vs 24m?",
  "file_id": "uuid",
  "species": "mouse",
  "session_history": [
    { "role": "user", "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

Response:

```json
{
  "reply": "Deterministic rendered text from tool results",
  "plots": [{ "url": "/plots/senescence_score.png", "caption": "..." }],
  "tool_calls": [
    {
      "name": "test_senescence_difference",
      "args": { "cell_type": "T cell", "reference_age": "3m", "comparison_age": "24m" },
      "result": { "...": "...", "inference_state": { "state": "LOW_POWER", ... } }
    }
  ]
}
```

### `POST /report`

Uses accumulated `tool_runs` from the frontend (authoritative). Optional `session_history` (user messages only for context).

```json
{
  "session_id": "string",
  "file_id": "uuid",
  "species": "mouse",
  "tool_runs": [],
  "plots": [{ "url": "/plots/umap.png" }]
}
```

Returns `report`, `report_url`, `pdf_url`.

### `GET /dataset/{file_id}/info?species=mouse`

Dataset summary (cell counts, ages, SenMayo coverage, metadata flags).

Static assets: `/plots/*`, `/reports/*`.

---

## Datasets

Large `.h5ad` files are not in git. After upload, copies are stored under `backend/data/uploads/{file_id}.h5ad`.

Tested with Tabula Muris Senis–style metadata (`age`, `cell_ontology_class`, `sample_id` or `mouse.id`).

---

## Tech stack

| Layer | Stack |
|--------|--------|
| API | FastAPI, Uvicorn |
| Analysis | Scanpy, AnnData, PyDESeq2, SciPy |
| Agent routing | Google Generative AI (`google-generativeai`) |
| Frontend | React, TypeScript, Vite, Tailwind |

---

## License

See [LICENSE](LICENSE).
