# Demo Script -- Senescence Agent

**Total time: ~6 minutes (3-min live demo + 3-min presentation)**

Practice this 10 times. Time every run. Must be under 6 minutes total.

---

## Segment 1: Opening Hook (15 seconds)

**Speaker: Aviral**

> "Biologists studying aging rely on specialized programming expertise most labs cannot afford. A bioinformatician costs $112,000 to $180,000 a year. We built the tool that closes that gap -- specialized for senescence detection in single-cell data."

---

## Segment 2: The Problem (30 seconds)

**Speaker: Aviral**

Show split screen:
- **Left:** A Scanpy script (~20 lines of Python code doing QC, clustering, SenMayo scoring)
- **Right:** One chat message: *"Find senescent cells in this aged mouse kidney dataset."*

> "This is what it takes to find senescent cells today -- 20 lines of Python, knowledge of Scanpy, AnnData, gene name conventions, and correct statistical methodology. With our tool, same result, one sentence, zero programming."

---

## Segment 3: Live Demo (3 minutes)

**Rodela drives the browser. Aviral narrates each step.**

### Step 1: Upload (15 sec)
- Rodela drags Tabula Muris Senis kidney .h5ad into the upload area
- Species dropdown: select "mouse"
- Click Upload

**Aviral narrates:** "We're uploading a Tabula Muris Senis kidney dataset -- 7,000+ cells from mice aged 3 to 24 months. The backend automatically runs quality control, normalization, and Leiden clustering."

### Step 2: Ask for senescence analysis (30 sec)
- Type: "Run the full senescence analysis"
- Wait for response

**Aviral narrates:** "One sentence. The agent automatically calls five tools in sequence: marker detection, SenMayo scoring, UMAP visualization, cluster annotation, and age comparison. Watch the tool calls appear in real time."

### Step 3: Show results (45 sec)
- Point to the UMAP colored by senescence score
- Point to the cluster rankings
- Point to the age comparison results

**Aviral narrates:** "The UMAP shows cells colored by SenMayo score -- red means higher senescence burden. The agent found that mesangial cells in cluster 12 show the highest senescence signal. And when we compare across ages, we see scores increase from 3-month to 24-month mice."

### Step 4: Ask a follow-up question (30 sec)
- Type: "What is the p-value for senescence difference in T cells, 3m vs 24m?"
- Wait for response

**Aviral narrates:** "Now we ask for a statistical test. The agent uses Mann-Whitney U on per-sample medians -- that's per-mouse, not per-cell -- which is the statistically correct approach. This avoids pseudoreplication, which is a common mistake in single-cell analysis."

### Step 5: Show the inference state (15 sec)
- Point to the inference state in the response (e.g., LOW_POWER or SIGNIFICANT)

**Aviral narrates:** "Notice the inference state. Our system automatically classifies every result into one of five states, from descriptive-only to statistically significant. If there aren't enough biological replicates, it tells you -- it never hallucinates a p-value."

### Step 6: Generate report (15 sec)
- Click "Download Report"
- Show the PDF briefly

**Aviral narrates:** "Every analysis generates a reproducible report with the complete tool call log, parameters, and results. This is an audit trail, not a summary written by the LLM."

---

## Segment 4: Architecture (45 seconds)

**Speaker: Aviral**

Show architecture diagram.

> "The architecture has three layers. The React frontend talks to a FastAPI backend. The backend uses Google Gemini for tool routing only -- the LLM picks which Scanpy tool to call, but it never generates the biology. Every tool returns facts-only JSON, which passes through our inference state machine -- that's the A through E system that prevents overclaiming. Finally, a deterministic template renderer produces the user-facing text. The LLM never writes the final answer."

---

## Segment 5: Novelty (30 seconds)

**Speaker: Aviral**

> "Three things make this different from existing tools like CellAgent or CompBioAgent:
> 1. We're senescence-specialized -- pre-loaded SenMayo signature, automatic mouse-human gene mapping, age-stratified analysis.
> 2. We enforce statistical rigor with an inference state machine that prevents the LLM from hallucinating significance.
> 3. Every result is deterministically rendered from tool facts -- not free-form LLM prose. You can reproduce every finding."

---

## Segment 6: Validation (30 seconds)

**Speaker: Aviral**

Show validation slide (GSE226225 results).

> "To validate our approach, we ran the agent on GSE226225 -- a dataset where senescent cells are explicitly labeled by the original researchers. Our SenMayo scoring identified [X]% of the labeled senescent cells. This isn't just a demo -- it's a scientific result."

---

## Segment 7: Limitations & Future Work (30 seconds)

**Speaker: Aviral**

> "We're transparent about limitations. This is RNA-seq only -- senescence is multi-modal. We've tested primarily on mouse data. And SenMayo coverage varies by tissue.
> Next steps: human clinical datasets, ATAC-seq integration for epigenetic markers, and custom gene signatures so researchers can define their own panels."

---

## Backup Plan

- Have backup demo video open in a browser tab BEFORE presenting
- If live demo fails at any point, switch to the video tab and narrate over it
- Record the backup video by Saturday June 27

---

## Pre-Demo Checklist

- [ ] Backend server running (`python main.py`)
- [ ] Frontend dev server running (`npm run dev`)
- [ ] `.env` file has valid GEMINI_API_KEY
- [ ] TMS kidney dataset already uploaded (have the file_id ready)
- [ ] Backup video tab open
- [ ] Browser zoom at 125% for audience visibility
- [ ] Close all notifications and chat apps
