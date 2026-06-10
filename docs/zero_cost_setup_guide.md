# Zero-Cost Setup Guide -- Google Colab / Kaggle

Everything here costs $0. No paid APIs, no cloud instances, no paid tiers.

---

## Cost Breakdown

| Resource | Free Tier | What You Need |
|----------|-----------|---------------|
| Google Colab | CPU runtime, 12GB RAM, ~100GB disk | Backend + analysis |
| Kaggle Notebooks | CPU/GPU, 16GB RAM, ~70GB disk | Alternative to Colab |
| Gemini API | Free tier: 15 RPM, 1M tokens/day | Agent tool routing |
| GitHub | Unlimited public repos | Code hosting |
| Google Drive | 15GB free | Dataset storage |
| Google Slides | Free | Presentation |
| Google Docs | Free | Research narrative |
| Netlify/Vercel | Free tier | Frontend hosting (optional) |

---

## STEP 1: Get a Free Gemini API Key

### Why
The agent uses Google Gemini to decide which Scanpy tool to call. Gemini 2.5 Flash has a generous free tier (15 requests/minute, 1 million tokens/day). This is more than enough for a hackathon demo.

### How
1. Go to https://aistudio.google.com/apikey
2. Sign in with your Google account (use your personal Gmail, not USF -- some edu accounts have restrictions)
3. Click "Create API Key"
4. Select "Create API key in new project" (or use an existing project)
5. Copy the key -- it looks like `AIzaSy...` (39 characters)
6. **Save it somewhere safe** -- you'll need it in Step 3

### Verify it works
Open any Python environment and run:
```python
import google.generativeai as genai
genai.configure(api_key="YOUR_KEY_HERE")
model = genai.GenerativeModel("gemini-2.5-flash")
response = model.generate_content("Say hello")
print(response.text)
```
If you see a response, your key works.

---

## STEP 2: Download the Datasets (One Time)

### Why
The agent analyzes `.h5ad` single-cell datasets. You need at least one for development and demo, plus the validation dataset for your presentation slides.

### What to Download

#### Dataset 1: Tabula Muris Senis -- Kidney (Primary Demo Dataset)
- **Size:** ~150-300 MB
- **Source:** https://figshare.com/projects/Tabula_Muris_Senis/64982
- **Direct file:** Look for `tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad`
- **Alternative source:** https://cellxgene.cziscience.com/collections/0b9d8a04-bb9d-44da-aa27-705bb65b54eb
  - Filter by "Kidney" tissue, download the FACS `.h5ad`

#### Dataset 2: Tabula Muris Senis -- Lung or Spleen (Second Demo Dataset)
- **Size:** ~100-250 MB
- Same sources as above, filter for "Lung" or "Spleen"

#### Dataset 3: GSE226225 (Validation -- for your presentation slides)
- **Source:** https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE226225
- Click "Supplementary file" to find the processed data
- You need the `.h5ad` or expression matrix with senescence labels

### How to Download to Google Drive
**Option A -- Download to your computer first, then upload:**
1. Download the files to your computer
2. Go to https://drive.google.com
3. Create a folder: `senescence-agent-data`
4. Upload the `.h5ad` files there

**Option B -- Download directly in Colab (faster):**
```python
# In a Colab cell:
!pip install gdown
import gdown

# If the file is on Figshare or a direct URL:
!wget -O /content/drive/MyDrive/senescence-agent-data/kidney.h5ad "DIRECT_DOWNLOAD_URL"
```

**Option C -- Use cellxgene census (programmatic, no manual download):**
```python
# This downloads TMS data programmatically
import cellxgene_census
census = cellxgene_census.open_soma()
# Query specific tissue/dataset
```

### Space Management
- Google Drive free: 15 GB
- Each TMS organ: 150-300 MB
- 3 datasets: ~600 MB-1 GB total
- You have plenty of room

---

## STEP 3: Set Up the Backend on Google Colab

### Why
Colab gives you a free Python environment with enough RAM (12 GB) to load single-cell datasets and run Scanpy. The backend (FastAPI + agent) runs here.

### How

#### 3a. Open a new Colab notebook
1. Go to https://colab.research.google.com
2. Click "New Notebook"
3. Rename it: `senescence_agent_backend`
4. **Runtime > Change runtime type > CPU** (no GPU needed -- Scanpy runs on CPU)

#### 3b. Mount Google Drive (for datasets)
```python
# Cell 1: Mount Drive
from google.colab import drive
drive.mount('/content/drive')
```
Click the authorization link and allow access.

#### 3c. Clone the repo
```python
# Cell 2: Clone repo
!git clone https://github.com/Ro-netizen004/senescence-agent.git /content/senescence-agent
%cd /content/senescence-agent/backend
```

#### 3d. Install Python dependencies
```python
# Cell 3: Install packages (~3-5 minutes first time)
!pip install -q \
  fastapi==0.136.1 \
  uvicorn==0.46.0 \
  python-multipart==0.0.28 \
  python-dotenv==1.2.2 \
  google-generativeai>=0.8.3 \
  anndata==0.11.4 \
  scanpy==1.11.5 \
  leidenalg==0.11.0 \
  pydeseq2>=0.4.4 \
  mygene==3.2.2 \
  pyngrok
```

#### 3e. Set up the API key
```python
# Cell 4: Configure API key
import os
os.environ["GEMINI_API_KEY"] = "YOUR_KEY_HERE"  # <-- paste your key
os.environ["GEMINI_MODEL"] = "gemini-2.5-flash"

# Write .env file for the backend
with open("/content/senescence-agent/.env", "w") as f:
    f.write(f'GEMINI_API_KEY={os.environ["GEMINI_API_KEY"]}\n')
    f.write(f'GEMINI_MODEL=gemini-2.5-flash\n')

print("API key configured")
```

#### 3f. Copy dataset to backend data folder
```python
# Cell 5: Link or copy your dataset
import shutil, os

src = "/content/drive/MyDrive/senescence-agent-data/kidney.h5ad"
dst = "/content/senescence-agent/backend/data/tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"

if os.path.exists(src):
    # Symlink saves disk space
    os.symlink(src, dst)
    print(f"Linked: {dst}")
else:
    print(f"Dataset not found at {src}")
    print("Upload it to Google Drive first (see Step 2)")
```

#### 3g. Start the FastAPI server with ngrok
```python
# Cell 6: Start backend with public URL
from pyngrok import ngrok
import subprocess, time

# Get a free ngrok auth token at https://ngrok.com (sign up free)
# Then run: ngrok.set_auth_token("YOUR_NGROK_TOKEN")

# Start uvicorn in the background
proc = subprocess.Popen(
    ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
    cwd="/content/senescence-agent/backend",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

time.sleep(5)  # Wait for server to start

# Create public URL
public_url = ngrok.connect(8000)
print(f"\n{'='*60}")
print(f"Backend is live at: {public_url}")
print(f"{'='*60}")
print(f"\nHealth check: {public_url}/health")
print(f"Use this URL as VITE_API_URL for the frontend")
```

#### Alternative: Run without ngrok (Colab-only testing)
```python
# Cell 6 alternative: Test the agent directly in Python (no server needed)
import sys
sys.path.insert(0, "/content/senescence-agent/backend")

from agent.agent import run_agent
from agent.cache import cache_adata
import scanpy as sc

# Load dataset
adata = sc.read_h5ad("/content/drive/MyDrive/senescence-agent-data/kidney.h5ad")
file_id = "test-kidney"
cache_adata(file_id, adata)

# Test the agent
result = run_agent(
    session_history=[],
    message="Run the full senescence analysis",
    file_id=file_id,
    species="mouse"
)

print("Reply:", result["reply"][:500])
print("\nPlots:", result["plots"])
print("\nTools called:", [t["name"] for t in result["tool_calls"]])
```

---

## STEP 4: Set Up the Frontend

### Why
The React frontend is what judges see. You have three options, from simplest to most polished.

### Option A: Run Frontend Locally on Your Laptop (Recommended for Demo)

This is the best option for the live demo -- it runs fast and you control it.

1. Install Node.js 18+ from https://nodejs.org (free)
2. Open a terminal:
```bash
cd C:\Users\avira\senescence-agent\frontend

# Install dependencies
npm install

# Create .env with the Colab backend URL
echo VITE_API_URL=https://your-ngrok-url.ngrok.io > .env

# Start the dev server
npm run dev
```
3. Open http://localhost:5173 in your browser

### Option B: Run Frontend on Colab Too (All-in-One)

Add this to your Colab notebook after the backend is running:
```python
# Cell 7: Build and serve frontend
%cd /content/senescence-agent/frontend

# Install Node.js in Colab
!curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
!sudo apt-get install -y nodejs

# Install frontend dependencies
!npm install

# Set the API URL to the ngrok backend
!echo "VITE_API_URL={public_url}" > .env

# Build for production
!npm run build

# Serve the built frontend
!npm install -g serve
!nohup serve -s dist -l 3000 &

# Create public URL for frontend
frontend_url = ngrok.connect(3000)
print(f"\n{'='*60}")
print(f"Frontend is live at: {frontend_url}")
print(f"{'='*60}")
```

### Option C: Deploy Frontend to Netlify (Free, Permanent URL)

1. Build the frontend locally:
```bash
cd frontend
echo "VITE_API_URL=https://your-ngrok-url.ngrok.io" > .env
npm run build
```
2. Go to https://app.netlify.com (sign up free with GitHub)
3. Drag the `frontend/dist` folder onto the deploy area
4. You get a permanent URL like `https://your-app.netlify.app`

**Warning:** The backend URL changes every time you restart Colab, so you'll need to rebuild with the new URL.

---

## STEP 5: Test End-to-End

### Why
You need to verify upload → chat → plot → report works before the demo.

### How

1. Open the frontend (localhost:5173 or your deployed URL)
2. Select "Mouse" from the species dropdown
3. Click the upload area and select your kidney `.h5ad` file
4. Wait for "Dataset loaded" confirmation
5. Type: `Run the full senescence analysis`
6. Wait 20-30 seconds for the response
7. You should see:
   - A text response with cluster scores
   - UMAP plot(s) in the plots panel
   - Tool call log showing which tools ran
8. Type: `What is the p-value for senescence in T cells, 3m vs 24m?`
9. Click "Report" button to generate a report
10. Verify the PDF downloads

### If Something Fails
- **"Dataset not found"**: The .h5ad file wasn't copied correctly. Check the symlink/path.
- **"GEMINI_API_KEY not configured"**: The .env file isn't being read. Check the path.
- **Timeout errors**: Colab may be slow on first run (gene name conversion). Try again.
- **CORS errors**: Make sure the frontend URL matches what's in CORS config. Add your ngrok URL if needed.

---

## STEP 6: Run the Validation Analysis (For Your Slides)

### Why
The validation slide (GSE226225) is the difference between "a demo" and "a scientific result." This is your strongest slide.

### How

```python
# In Colab, after the backend is loaded:
import scanpy as sc
import numpy as np

# Load the validation dataset
adata = sc.read_h5ad("/content/drive/MyDrive/senescence-agent-data/GSE226225.h5ad")
print(f"Loaded: {adata.shape[0]} cells, {adata.shape[1]} genes")
print(f"Columns: {list(adata.obs.columns)}")

# Check for senescence labels
# (The column name depends on the dataset -- inspect adata.obs.columns)
# Common names: "senescence", "senescent", "condition", "group"
```

Once you find the label column, use the code from `docs/validation_and_comparison.md` to compute overlap percentages.

---

## STEP 7: Download Datasets Directly in Colab (If You Don't Want to Use Drive)

### Tabula Muris Senis via cellxgene
```python
!pip install -q cellxgene-census

import cellxgene_census
import scanpy as sc

# Open the census
census = cellxgene_census.open_soma(census_version="2023-12-15")

# Get kidney data from Tabula Muris Senis
adata = cellxgene_census.get_anndata(
    census,
    organism="Mus musculus",
    obs_value_filter="dataset_id == 'YOUR_DATASET_ID' and tissue_general == 'kidney'",
)

adata.write_h5ad("/content/senescence-agent/backend/data/kidney.h5ad")
print(f"Saved: {adata.shape}")
```

### Direct Download from Figshare
```python
# Tabula Muris Senis FACS datasets
!wget -q -O /content/kidney.h5ad "https://ndownloader.figshare.com/files/XXXXX"
# (Replace XXXXX with the actual Figshare file ID -- find it on the Figshare page)
```

---

## STEP 8: Create Your Presentation (Google Slides -- Free)

### Why
Google Slides is free, collaborative, and easy to share with Rodela and Fei He.

### How
1. Go to https://slides.google.com
2. Create a new presentation
3. Follow the outline in `docs/presentation_outline.md` (13 slides)
4. For each slide:
   - Copy the content from the outline
   - Take screenshots from the running app
   - Add screenshots as images

### Slide-by-Slide Content Sources

| Slide | Content Source |
|-------|---------------|
| 1. Title | `docs/presentation_outline.md` Slide 1 |
| 2. The Problem | `docs/demo_script.md` Segment 2 |
| 3. Why Senescence | `docs/project_description.md` "Why Senescence" section |
| 4. Live Demo | Screenshots from the running app |
| 5. Architecture | Diagram from `docs/research_narrative.md` Section 4.1 |
| 6. Marker Genes | Table from `docs/presentation_outline.md` Slide 6 |
| 7. Novelty | Comparison table from `docs/presentation_outline.md` Slide 7 |
| 8. Validation | Results from Step 6 above |
| 9. Comparison | Results from `docs/validation_and_comparison.md` |
| 10. Limitations | `docs/research_narrative.md` Section 6 |
| 11. User Quote | Captured in Week 6 user test |
| 12. Team | Your names + Fei He |
| 13. Q&A | `docs/qa_answers.md` (keep as personal reference) |

---

## STEP 9: Set Up the Google Doc (Research Narrative)

### Why
Shared doc for you and Rodela to collaborate on research writing. Fei He can also review it.

### How
1. Go to https://docs.google.com
2. Create: "Senescence Agent -- Research Narrative"
3. Copy the entire contents of `docs/research_narrative.md` into it
4. Share with Rodela (edit access) and Fei He (comment access)
5. Share link with Rodela

---

## STEP 10: Record the Backup Demo Video (Free)

### Why
If the live demo crashes, you switch to a pre-recorded video. This is your safety net.

### How

**Option A: OBS Studio (free, best quality)**
1. Download from https://obsproject.com
2. Record your screen while running the demo script
3. Export as MP4

**Option B: Windows built-in (simplest)**
1. Press `Win + G` to open Game Bar
2. Click the record button
3. Run through the demo
4. Video saves to `Videos\Captures`

**Option C: Loom (free tier, shareable link)**
1. Install from https://www.loom.com
2. Record screen + optional webcam
3. Get a shareable link

### What to Record
Follow `docs/demo_script.md` exactly:
1. Upload dataset → 2. "Run the full senescence analysis" → 3. Show results → 4. Ask for p-value → 5. Show inference state → 6. Download report

Keep it under 3 minutes. Save to `docs/backup_demo.mp4`.

---

## Kaggle Alternative (If Colab Doesn't Work)

### Why Use Kaggle Instead
- 16 GB RAM (vs Colab's 12 GB) -- better for large datasets
- 30 hours/week of GPU (not needed, but nice to have)
- 70 GB disk
- More stable sessions (Colab disconnects after idle)

### How
1. Go to https://www.kaggle.com
2. Sign up (free) or sign in
3. Click "Code" > "New Notebook"
4. In Settings (right panel): turn on "Internet" access
5. Use the same cells as the Colab guide above
6. For API key, use Kaggle Secrets:
   - Settings > "Add Secret" > Name: `GEMINI_API_KEY`, Value: your key
   ```python
   from kaggle_secrets import UserSecretsClient
   secrets = UserSecretsClient()
   os.environ["GEMINI_API_KEY"] = secrets.get_secret("GEMINI_API_KEY")
   ```

### Kaggle Dataset Upload
1. Go to https://www.kaggle.com/datasets
2. Click "New Dataset"
3. Upload your .h5ad files
4. In your notebook, the dataset appears at `/kaggle/input/your-dataset-name/`

---

## Quick Reference: Free Tools Used

| Tool | What For | URL |
|------|----------|-----|
| Google Colab | Backend + analysis | colab.research.google.com |
| Kaggle Notebooks | Alternative to Colab | kaggle.com/code |
| Gemini API (free) | Agent LLM routing | aistudio.google.com/apikey |
| GitHub | Code hosting | github.com |
| Google Drive | Dataset storage | drive.google.com |
| Google Slides | Presentation | slides.google.com |
| Google Docs | Research writing | docs.google.com |
| ngrok (free tier) | Public URL for Colab | ngrok.com |
| Node.js | Frontend (local) | nodejs.org |
| OBS Studio | Demo recording | obsproject.com |
| Netlify (free) | Frontend hosting | netlify.com |

**Total cost: $0**

---

## Troubleshooting

### "Colab disconnected / runtime reset"
- Colab free tier disconnects after ~90 min idle or ~12 hours total
- **Solution:** Re-run all cells from the top. Your datasets on Drive persist.
- **For the demo:** Start the notebook 15 min before presenting. Don't leave it idle.

### "Out of memory"
- TMS full datasets can be large. If you hit 12GB RAM limit:
```python
# Subsample the dataset
adata = sc.read_h5ad("kidney.h5ad")
sc.pp.subsample(adata, n_obs=5000)  # Keep 5000 cells
adata.write_h5ad("kidney_small.h5ad")
```

### "Gemini rate limit"
- Free tier: 15 requests/minute
- Each chat message = 1-5 requests (tool routing loop)
- **Solution:** Wait 60 seconds between rapid-fire requests
- For the demo, this is never an issue (you only send ~6 messages)

### "ngrok tunnel expired"
- Free ngrok tunnels expire after 2 hours
- **Solution:** Restart the tunnel: `ngrok.connect(8000)`
- For the demo: start ngrok right before presenting

### "Frontend can't connect to backend"
- CORS issue or wrong URL
- **Solution:** Add the ngrok URL to CORS in main.py:
```python
# In Colab, before starting the server:
import fileinput
for line in fileinput.input("/content/senescence-agent/backend/main.py", inplace=True):
    if '"http://localhost:5174"' in line:
        print(line.rstrip())
        print(f'        "{public_url}",')
    else:
        print(line, end='')
```

### "MyGene API timeout on first load"
- Gene name conversion calls MyGene API at server startup
- **Solution:** It only runs once and caches. Wait ~30 seconds.
- If it consistently fails, the fallback dictionary handles the 10 key genes.
