from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, List, Optional
import os
import uuid
import shutil
import scanpy as sc

from agent.agent import run_agent
from agent.report import generate_report, save_report_files
from agent.cache import cache_adata
from dataset_paths import persist_upload, resolve_dataset_path, ensure_uploads_dir
from tools.dataset_info import build_dataset_summary

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for plots
OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
app.mount("/plots", StaticFiles(directory=OUTPUTS_DIR), name="plots")

REPORTS_DIR = os.path.join(OUTPUTS_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")

# Server-side session store
sessions: dict = {}
session_tool_runs: dict[str, list] = {}

ensure_uploads_dir()

# ── Models ─────────────────────────────────────────────────────────────────
class HistoryMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    session_id: str
    message: str
    file_id: str
    species: str
    session_history: Optional[List[HistoryMessage]] = []  # from frontend

class ToolRunRecord(BaseModel):
    name: str
    args: Optional[dict] = None
    result: Optional[Any] = None


class ReportRequest(BaseModel):
    session_id: str
    file_id: str
    species: str
    session_history: Optional[List[HistoryMessage]] = []
    tool_runs: Optional[List[ToolRunRecord]] = []
    plots: Optional[list[dict]] = []

# ── Upload ──────────────────────────────────────────────────────────────────
@app.post("/upload")
async def upload_file(
    file: UploadFile,
    species: str = Form(...)
):
    if not file.filename.endswith(".h5ad"):
        raise HTTPException(
            status_code=400,
            detail="Only .h5ad files are allowed"
        )

    file_id = str(uuid.uuid4())
    temp_path = os.path.join(ensure_uploads_dir(), f"{file_id}.uploading")

    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_path = persist_upload(file_id, temp_path)
    os.remove(temp_path)

    print(f"Uploaded file: {file_id} ({file.filename}) -> {file_path}")
    return {"file_id": file_id, "species": species}

# ── Chat ────────────────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.file_id or not request.message:
        raise HTTPException(status_code=400, detail="Missing required fields")

    file_path = resolve_dataset_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Dataset not found. Please upload again.")

    # Use frontend history if provided, otherwise fall back to server sessions
    # Frontend history is source of truth — it has correct role names
    if request.session_history:
        session_history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.session_history
            if msg.role in ("user", "assistant", "system", "tool")  # sanitize here too
        ]
    else:
        # Fallback: server-side session store
        if request.session_id not in sessions:
            sessions[request.session_id] = []
        session_history = sessions[request.session_id]

    try:
        response = run_agent(
            session_history=session_history,
            message=request.message,
            file_id=request.file_id,
            species=request.species
        )
    except Exception as e:
        print(f"Agent error: {e}")
        return {
            "reply": f"Something went wrong: {str(e)}",
            "plots": [],
            "tool_calls": []
        }

    # Update server-side session with correct role names
    if request.session_id not in sessions:
        sessions[request.session_id] = []

    sessions[request.session_id].append({
        "role": "user",
        "content": request.message
    })
    sessions[request.session_id].append({
        "role": "assistant",        # was "agent" — this was the bug
        "content": response.get("reply", "")
    })

    for tool_call in response.get("tool_calls") or []:
        session_tool_runs.setdefault(request.session_id, []).append(tool_call)

    return response

@app.post("/report")
async def report(request: ReportRequest):
    if not request.file_id:
        raise HTTPException(status_code=400, detail="Missing dataset")

    file_path = resolve_dataset_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Dataset not found. Please upload again.")

    session_history = [
        {"role": msg.role, "content": msg.content}
        for msg in (request.session_history or [])
        if msg.role == "user"
    ]

    if request.tool_runs:
        tool_runs = [run.model_dump() for run in request.tool_runs]
    else:
        tool_runs = session_tool_runs.get(request.session_id, [])

    try:
        plot_urls = [
            plot.get("url")
            for plot in request.plots or []
            if isinstance(plot, dict) and plot.get("url")
        ]
        plot_paths = [
            os.path.join(OUTPUTS_DIR, os.path.basename(url))
            for url in plot_urls
        ]

        report_text = generate_report(
            file_id=request.file_id,
            species=request.species,
            tool_runs=tool_runs,
            session_history=session_history,
        )
        report_files = save_report_files(
            report_text,
            REPORTS_DIR,
            plot_paths=plot_paths,
            plot_urls=plot_urls,
        )
    except Exception as e:
        print(f"Report error: {e}")
        return {"report": f"Report generation failed: {str(e)}"}

    if request.session_id not in sessions:
        sessions[request.session_id] = []

    sessions[request.session_id].append({
        "role": "assistant",
        "content": report_text
    })

    return {
        "report": report_text,
        "report_url": f"/reports/{os.path.basename(report_files['markdown_path'])}",
        "pdf_url": f"/reports/{os.path.basename(report_files['pdf_path'])}",
    }

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


@app.get("/dataset/{file_id}/info")
async def dataset_info(file_id: str, species: str = "mouse"):
    file_path = resolve_dataset_path(file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Dataset not found. Please upload again.")

    adata = sc.read_h5ad(file_path)
    summary = build_dataset_summary(adata, species)
    cache_adata(file_id, adata)
    return summary


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
