# senescence-agent
LLM-powered AI agent for single-cell RNA sequencing analysis — identifies senescent cell populations in aging datasets using natural language, no coding required.

## Local setup

### Backend
1. Open a terminal in `backend/`
2. Install Python dependencies:
   - `pip install -r requirements.txt`
3. Start the server:
   - `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

The backend listens on `http://localhost:8000`.

### Frontend
1. Open a terminal in `frontend/`
2. Install Node dependencies:
   - `npm install`
3. Start the Vite dev server:
   - `npm run dev`

The frontend runs on `http://localhost:5173` and is configured to talk to the backend via CORS.
