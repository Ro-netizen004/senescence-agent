from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import tempfile
import os
import uuid
import shutil

from agent.agent import run_agent

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React Vite frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files route for plots
OUTPUTS_DIR = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)
app.mount("/plots", StaticFiles(directory=OUTPUTS_DIR), name="plots")

# Session management
sessions = {}

# Utility function
def capitalize_if_mouse(gene: str, species: str) -> str:
    """Utility to map gene names based on species."""
    if species.lower() == 'mouse':
        return gene.capitalize()
    return gene.upper()

class ChatRequest(BaseModel):
    session_id: str
    message: str
    file_id: str
    species: str

@app.post("/upload")
async def upload_file(
    file: UploadFile,
    species: str = Form(...)
):
    if not file.filename.endswith(".h5ad"):
        raise HTTPException(status_code=400, detail="Only .h5ad files are allowed")

    file_id = str(uuid.uuid4())
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, f"{file_id}.h5ad")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"file_id": file_id}

@app.post("/chat")
async def chat(request: ChatRequest):
    if not request.file_id or not request.message:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    file_path = os.path.join(tempfile.gettempdir(), f"{request.file_id}.h5ad")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File ID not found")

    if request.session_id not in sessions:
        sessions[request.session_id] = []
    
    session_history = sessions[request.session_id]
    session_history.append({"role": "user", "content": request.message})

    # This is where we might extract genes and format them, 
    # but for simplicity, the agent will handle that logic using the species info
    # Example usage just to show it exists:
    # formatted_gene = capitalize_if_mouse("CDKN1A", request.species)

    # Call Rodela's Agent
    response = run_agent(
        session_history=session_history,
        message=request.message,
        file_id=request.file_id,
        species=request.species
    )

    session_history.append({"role": "agent", "content": response.get("reply", "")})
    
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)