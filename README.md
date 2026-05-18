# senescence-agent
LLM-powered AI agent for single-cell RNA sequencing analysis — identifies senescent cell populations in aging datasets using natural language, no coding required.

## API Contract (Agreed upon with Agent Team)
To ensure seamless integration between the React frontend and the LLM Agent, the backend FastAPI server exposes the following interface:

### 1. `/upload` (POST)
Accepts a multipart form dataset upload.
- **Request (FormData)**:
  - `file`: The `.h5ad` single-cell dataset.
  - `species`: String (e.g., `"mouse"` or `"human"`).
- **Response**:
  - `{"file_id": "uuid-string"}`

### 2. `/chat` (POST)
The primary interaction endpoint for natural language analysis.
- **Request (JSON)**:
  ```json
  {
    "session_id": "string",
    "message": "string (e.g. 'Can you score senescence?')",
    "file_id": "uuid-string",
    "species": "string (e.g. 'mouse')"
  }
  ```
- **Response (JSON)**:
  ```json
  {
    "reply": "string (Agent's text response)",
    "plots_generated": ["list of plot filenames (e.g. 'umap.png')"]
  }
  ```
