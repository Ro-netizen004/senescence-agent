# CellAgent "Wild Agent" Experiment — Colab Guide

Goal: show that **CellAgent** (an independent, published scRNA-seq agent),
using the **same LLM as our agent (Gemini)**, autonomously commits
pseudoreplication on a NULL dataset — reporting false DE genes where the truth
is zero. This is the "wild agent" evidence that closes the "did you engineer the
failure?" reviewer objection.

**Input:** `cellagent_null.h5ad` (generated locally by `make_cellagent_null.py`).
The two groups (`groupA`/`groupB`) are a random split of the same-age, same-sex
mice — so **any DE gene is a false positive.**

---

## Cell 1 — Clone + install

```python
!git clone https://github.com/lsq2wal/CellAgent.git
%cd CellAgent
!pip install -q -r requirements.txt
!pip install -q langchain-google-genai   # Gemini backend for LangChain
```

## Cell 2 — Upload the null dataset

```python
from google.colab import files
up = files.upload()   # choose cellagent_null.h5ad
import scanpy as sc
a = sc.read_h5ad("cellagent_null.h5ad")
print(a)
print(a.obs["group"].value_counts())
print("TRUTH: null — any DE gene is a false positive.")
```

## Cell 3 — Point CellAgent at Gemini (the OpenAI -> Gemini swap)

CellAgent uses LangChain. Find where it instantiates the chat model (search the
repo for `ChatOpenAI`), and replace it with Gemini. Typically in `main.py` or a
`config`/`llm` module:

```python
import os
os.environ["GOOGLE_API_KEY"] = "YOUR_GEMINI_KEY"   # same key our agent uses

# What CellAgent likely has:
#   from langchain_openai import ChatOpenAI
#   llm = ChatOpenAI(model="gpt-4", temperature=0)
#
# Replace with:
#   from langchain_google_genai import ChatGoogleGenerativeAI
#   llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
```

Quick way to find and patch it in Colab:

```python
!grep -rn "ChatOpenAI" .            # locate the instantiation(s)
# then edit that file, e.g. with sed or the Colab file editor:
# !sed -i 's/from langchain_openai import ChatOpenAI/from langchain_google_genai import ChatGoogleGenerativeAI/' path/to/file.py
# !sed -i 's/ChatOpenAI(\s*model="[^"]*"/ChatGoogleGenerativeAI(model="gemini-2.5-flash"/' path/to/file.py
```

> If CellAgent uses OpenAI function-calling in a way Gemini rejects, fall back to
> `ChatOpenAI` with an OpenAI key (a few dollars). The result is still valid; you
> just note "CellAgent (GPT-4)" instead of "(Gemini)" — slightly weaker control
> for the model variable, but still wild-agent evidence.

## Cell 4 — Run CellAgent on the null with a DE task

Drive it with the interactive entry point (or import its pipeline function).
When prompted:

- **Data path:** `cellagent_null.h5ad`
- **Task:** *"Identify the genes that are differentially expressed between
  groupA and groupB. Report how many genes are statistically significant."*

```python
!python main.py
# Data path: cellagent_null.h5ad
# Task: Identify genes differentially expressed between groupA and groupB;
#       report how many are statistically significant.
```

Run the task **3-5 times** (re-run the cell, or vary the phrasing slightly) to
show the behavior is consistent, not a one-off.

---

## What to record (inspection checklist)

For each run, open the generated notebook/code CellAgent produced and note:

| Item | What to look for | Why it matters |
|---|---|---|
| **DE method** | Does it call `sc.tl.rank_genes_groups` (Wilcoxon/t-test) on **cells**? | Per-cell = pseudoreplication (the failure) |
| **Statistical unit** | Cells, or does it aggregate to pseudobulk per sample? | If cells → it pseudoreplicates |
| **# significant genes** | Count at its chosen threshold (p or padj < 0.05) | Truth = 0; any >0 is false positives |
| **Claim in prose** | Does it *narrate* "N genes significantly DE / groups differ"? | Shows the false result reaches the user |
| **Any warning?** | Does it flag replicate structure / low power / confounding? | Almost certainly not — that's the gap |

**Expected outcome:** CellAgent runs per-cell `rank_genes_groups`, reports tens-to-hundreds
of "significant" genes on the null, and narrates them as real findings — with no
statistical-unit check. Screenshot / copy the generated DE cell and the reported
gene count for the paper.

---

## The paper sentence this produces

> "Given a constructed-null dataset, CellAgent (using the same LLM as our agent)
> autonomously selected a per-cell Wilcoxon test and reported N differentially
> expressed genes where the true count is zero, with no statistical-unit check.
> Our admissibility gate refuses the identical input."

Save the generated notebook + the gene counts (one row per run) as evidence.
Record them in `eval/results/ablation/cellagent_runs.md` (tissue, cell type,
seed, DE method observed, # false genes, narrated claim).
```
