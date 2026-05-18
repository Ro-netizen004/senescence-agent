# senescence-agent

LLM-powered AI agent for single-cell RNA sequencing analysis.  
The system identifies senescent cell populations in aging datasets using natural language — no coding required.

---

# Project Structure

```text
senescence-agent/
│
├── backend/        # FastAPI backend + Scanpy analysis tools
├── frontend/       # React + TypeScript frontend
├── data/           # Local datasets (.h5ad) — ignored by git
├── outputs/        # Generated plots and analysis outputs
├── agent/          # LLM orchestration logic
└── README.md
```

---

# Features

- Single-cell RNA-seq preprocessing
- Quality control filtering
- Clustering with Leiden algorithm
- UMAP visualization
- Senescence marker detection
- Natural language interaction through LLM agent
- Support for aging datasets (e.g. Tabula Muris Senis)

---

# API Contract (Agreed with Frontend + Agent Team)

To ensure seamless integration between the React frontend and the LLM agent, the backend FastAPI server exposes the following endpoints.

---

## 1. `/upload` — Upload Dataset

### Method
`POST`

### Description
Accepts a `.h5ad` single-cell dataset upload.

### Request (multipart/form-data)

| Field | Type | Description |
|---|---|---|
| file | File | `.h5ad` dataset |
| species | String | `"mouse"` or `"human"` |

### Response

```json
{
  "file_id": "uuid-string"
}
```

---

## 2. `/chat` — Natural Language Analysis

### Method
`POST`

### Description
Main interaction endpoint for running AI-assisted analysis.

### Request (JSON)

```json
{
  "session_id": "string",
  "message": "Can you score senescence?",
  "file_id": "uuid-string",
  "species": "mouse"
}
```

### Response (JSON)

```json
{
  "reply": "Agent analysis response",
  "plots_generated": [
    "umap.png"
  ]
}
```

---

# Local Development

## Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

---

# Datasets

This project currently uses:

- PBMC3K (Scanpy demo dataset)
- Tabula Muris Senis (mouse aging atlas)

Datasets are not stored in GitHub because of large file sizes.

Download datasets manually into:

```text
backend/data/
```

---

# Tech Stack

## Backend
- Python
- Scanpy
- AnnData
- FastAPI
- Uvicorn

## Frontend
- React
- TypeScript
- Vite

## AI
- Ollama
- Llama 3.1 8B