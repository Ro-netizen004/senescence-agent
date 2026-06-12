# API Examples for Senescence Agent Backend

Test the FastAPI backend without the frontend using these examples.

## Base URL

```
http://localhost:8000
```

Start the server: `cd backend && python main.py`

---

## 1. Health Check (`GET /health`)

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "gemini_configured": true
}
```

---

## 2. Upload Dataset (`POST /upload`)

Upload an `.h5ad` file with a species parameter.

### cURL
```bash
curl -X POST "http://localhost:8000/upload" \
  -F "file=@/path/to/dataset.h5ad" \
  -F "species=mouse"
```

### PowerShell
```powershell
$form = @{
    file = Get-Item "C:\path\to\dataset.h5ad"
    species = "mouse"
}
Invoke-RestMethod -Uri "http://localhost:8000/upload" -Method Post -Form $form
```

Response:
```json
{
  "file_id": "b3c97e1a-83b6-49a3-9529-5d204a37bfa2",
  "species": "mouse"
}
```

---

## 3. Dataset Info (`GET /dataset/{file_id}/info`)

```bash
curl "http://localhost:8000/dataset/b3c97e1a-83b6-49a3-9529-5d204a37bfa2/info?species=mouse"
```

Response includes cell counts, age groups, SenMayo coverage, and available metadata columns.

---

## 4. Chat with Agent (`POST /chat`)

Send a natural-language message. The agent selects and runs Scanpy tools.

### cURL
```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-001",
    "message": "Run the full senescence analysis",
    "file_id": "b3c97e1a-83b6-49a3-9529-5d204a37bfa2",
    "species": "mouse"
}'
```

### PowerShell
```powershell
$body = @{
    session_id = "session-001"
    message = "Run the full senescence analysis"
    file_id = "b3c97e1a-83b6-49a3-9529-5d204a37bfa2"
    species = "mouse"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/chat" -Method Post -ContentType "application/json" -Body $body
```

Response:
```json
{
  "reply": "Standard senescence analysis panel completed.\n\n...",
  "plots": [
    { "url": "/plots/senescence_score.png", "caption": "senescence_score" },
    { "url": "/plots/umap.png", "caption": "generate_umap" }
  ],
  "tool_calls": [
    {
      "name": "find_senescence_markers",
      "args": {},
      "result": {
        "found_markers": ["Cdkn1a", "Cdkn2a", "Il6", ...],
        "coverage_pct": 52.8,
        "inference_state": { "state": "DESCRIPTIVE_ONLY", "state_id": "A" }
      }
    },
    {
      "name": "senescence_score",
      "args": {},
      "result": {
        "top_senescent_cluster": "12",
        "top_senescent_cell_type": "mesangial cell",
        "cluster_scores": { "12 (mesangial cell)": 0.2357, ... },
        "inference_state": { "state": "DESCRIPTIVE_ONLY", "state_id": "A" }
      }
    }
  ]
}
```

### Example queries to try

| Query | Expected tool(s) |
|-------|-----------------|
| "Run the full senescence analysis" | Panel: markers + score + UMAP + annotations + age |
| "Show me a UMAP" | generate_umap |
| "What is the p-value for T cells, 3m vs 24m?" | test_senescence_difference |
| "Run DESeq2 for macrophages" | run_deseq2 |
| "Which genes change with age in T cells?" | run_deseq2 |
| "Score senescence" | senescence_score |

---

## 5. Generate Report (`POST /report`)

```bash
curl -X POST "http://localhost:8000/report" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-001",
    "file_id": "b3c97e1a-83b6-49a3-9529-5d204a37bfa2",
    "species": "mouse",
    "tool_runs": [],
    "plots": [{"url": "/plots/senescence_score.png"}]
}'
```

Response:
```json
{
  "report": "# Senescence Analysis Report\n\n...",
  "report_url": "/reports/report_session-001.md",
  "pdf_url": "/reports/report_session-001.pdf"
}
```

---

## 6. View Plots (`GET /plots/{filename}`)

```bash
curl -O "http://localhost:8000/plots/senescence_score.png"
curl -O "http://localhost:8000/plots/umap.png"
curl -O "http://localhost:8000/plots/age_distribution.png"
curl -O "http://localhost:8000/plots/senescence_violin.png"
```

Or open directly in browser: `http://localhost:8000/plots/senescence_score.png`

---

## 7. Download Report Files

```
http://localhost:8000/reports/report_session-001.md
http://localhost:8000/reports/report_session-001.pdf
```

---

## Multi-turn Conversation

Include `session_history` to maintain context:

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session-001",
    "message": "Now test T cells specifically",
    "file_id": "b3c97e1a-83b6-49a3-9529-5d204a37bfa2",
    "species": "mouse",
    "session_history": [
      {"role": "user", "content": "Run the full senescence analysis"},
      {"role": "assistant", "content": "Standard senescence analysis panel completed..."}
    ]
}'
```
