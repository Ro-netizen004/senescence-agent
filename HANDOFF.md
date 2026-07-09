# Senescence Agent — Project Handoff

Status snapshot for continuing work in a fresh session. Repo:
`C:\Users\Tech moon\Documents\GitHub\senescence-agent` (Windows; venv Python at
`backend\venv\Scripts\python.exe`; run scripts from repo root).

---

## 1. What this project is

A **governed LLM agent for single-cell RNA-seq senescence analysis**, and a paper
about it. The research contribution is **statistical-validity governance**:
preventing LLM agents from committing **pseudoreplication** (treating individual
cells as independent replicates) and other invalid inferences.

**One-line claim:** current single-cell agents can commit pseudoreplication and
report hundreds of false discoveries; a deterministic two-gate "validity firewall"
prevents this without sacrificing real detection, validated against ground truth.

**Paper title:** *Faithful but Invalid: A Statistical-Validity Firewall for a
Governed Single-Cell Senescence Analysis Agent.*

**Target venue:** ML4H 2026, submission ~September. Proceedings (archival) track,
Findings as fallback. Paper `paper/paper.tex` + `custom.bib` — **compiles**.

---

## 2. The agent architecture (`backend/`)

Governed **single-LLM** pipeline (NOT multi-agent). The LLM only *proposes*
(intent/routing); all statistical computation, claim-permission, and user-facing
text are deterministic.

- **Three-tier routing:** (1) deterministic keyword router
  (`agent/intent_router.py`); (2) schema-constrained Gemini intent extraction +
  deterministic validation against the real dataset (`agent/intent_extractor.py`);
  (3) Gemini tool-calling fallback (`agent/agent.py`).
- **Gate 1 — Admissibility** (`agent/admissibility.py`): pre-execution. Refuses
  inadmissible inferences (no replicate column, <2 replicates/group, confounded
  contrast, circular) *before* the tool runs. Wired via `_gate` in
  `agent/tool_router.py`.
- **Gate 2 — Justification** (`agent/inference_state.py`): post-execution.
  Five-state machine (DESCRIPTIVE_ONLY, LOW_POWER, NOT_SIGNIFICANT,
  SIGNIFICANT_INFERENTIAL, BLOCKED) + `validity_flags` (cell_unit_not_inferential,
  circular_inference_risk, uncorrected_multiple_testing) that **override**
  significance — an inadmissible result cannot conclude even with a small p.
- **Deterministic renderer** (`agent/output_renderer.py`): no LLM prose for
  results; "interpretation firewall".
- **Governance toggle** (`agent/governance.py`): `AGENT_GOVERNANCE=off` enables the
  ungoverned ablation — per-cell tools (`tools/percell_inference.py`), no gates,
  LLM narration. Production always governed.
- **Rate limiter** (`agent/rate_limit.py`): `GEMINI_MAX_RPM` (currently 0 = off in
  `.env`; user is on paid Gemini tier, ~1000 RPM).
- Tools: `tools/senescence.py` (SenMayo scoring; NOTE the `use_raw=False` fix),
  `tools/statistics.py` (per-sample Mann-Whitney), `tools/run_deseq2.py` +
  `tools/build_pseudobulk.py` (pseudobulk DESeq2), `tools/age_analysis.py`.
- Pipeline (`agent/pipeline.py`) auto-detects pre-processed data (`adata.raw`
  present) and skips re-normalization (double-normalization bug fix).

---

## 3. Experiments (`eval/ablation/`, organized into subfolders)

All write to `eval/results/ablation/`. Scripts resolve repo root via
`Path(__file__).resolve().parents[3]`. See `eval/ablation/README.md`.

- **`null_harness/`** — Result 1. `null_harness.py` (one cell type) +
  `run_null_sweep.py` (all tissues). Constructed null via Squair et al. 2021
  method: randomly assign whole mice to two fake groups → truth = 0 DE genes.
  Per-cell Wilcoxon (ungoverned) vs pseudobulk (governed), counts false genes.
- **`power_preservation/`** — Result 2. `power_preservation.py`. GSE226225
  senescent-vs-control governed pseudobulk DE.
- **`cellagent/`** — wild-agent. `make_cellagent_null.py` (stratified same-age
  same-sex null), `run_ungoverned_agent.py`, `cellagent_colab.md`.
- **`transcripts/`** — `paired_transcripts.py`: same null prompt to governed vs
  ungoverned agent.
- **`governance/`** — `ablation_ism.py`, `ablation_pseudorep.py`,
  `ablation_router.py`, `run_all_ablations.py`.

Colab notebook for the CellAgent experiment: `notebooks/cellagent_experiment.ipynb`
(runnable; encodes the LangChain 0.3.x + numpy-force-reinstall + restart sequence).

---

## 4. Results (the headline numbers)

**Result 1 — governance prevents false discovery** (`null_sweep_summary.csv/.md`):
Across **5 TMS tissues × 13 cell types**, 200 perms each, on constructed nulls
(truth = 0):
- Ungoverned per-cell: **100% false-discovery rate in every one of 13 configs**,
  mean **1,425** false genes (range 63–5,748).
- Governed pseudobulk: mean **0.47** false genes, FDR rate ~2.5% (at/below α).
- **FDR correction does NOT fix it:** proximal tubule per-cell ~1,650 raw → ~916
  after FDR; pseudobulk ~176 raw → 0. The fix is the statistical *unit*.

**Result 2 — governance preserves power** (`power_preservation.json`): GSE226225
(55K cells; 11 senescent vs 2 non-senescent samples), governed pseudobulk
recovered **7,613** real DE genes with correct biology (CDKN1A +2.5, IL6 +1.6,
MMP3 +2.7, GDF15 +3.5 up; MKI67 −5.2, LMNB1 −5.4 down). The 2×2: governed silent
on nulls (0.47), detective on real (7,613) = calibration without accuracy loss.

**Aggregated-score robustness:** composite SenMayo score has between/within-mouse
variance ratio 0.17 → resists pseudoreplication; gene-level DE is where the
failure is severe (motivates the firewall's placement).

**Wild-agent (CellAgent)** (`cellagent_evidence.md`, `cellagent_run_log.txt`):
CellAgent (published agent, arXiv:2407.09811), driven by **the same LLM (Gemini)**,
autonomously **planned and executed** per-cell `rank_genes_groups` on the null and
**reported 36 false genes** (FDR<0.05, truth=0), ignoring the available `sample_id`
column. Number: CellAgent's own run = 36 (all genes, unfiltered); the exact null
split = 101 (detection-filtered); mean across splits = 221 (Table 1). Framed
honestly in the paper.

---

## 5. Positioning (literature-checked ~3× — gap holds)

- **EviBound** (arXiv:2511.05524) — governs *execution* (artifacts exist, run
  finished). A pseudoreplicated claim passes ALL its gates while being false =
  "faithful but invalid". Conceptual contrast, not run.
- **POPPER** (ICML 2025, arXiv:2502.09858) — Type-I control *across* a sequence of
  falsification experiments; not the statistical unit *within* a test.
- **Our gap:** statistical-unit validity gating as agent governance — uncovered.
- **Squair et al. 2021** (Nat Commun) — pseudoreplication + the constructed-null
  method we adopt (foundation/motivation).
- Others in `RELATED_WORK.md`: CellAgent, scPilot, scBench (2602.09063), BioDSA-1K
  (2505.16100), the dual-validity framework.

The honest framing: NOT a novel *method* (pseudobulk is textbook; governance
exists via EviBound/POPPER) — the contribution is the **falsifiable empirical
demonstration** (deployed agents fail; ground-truth-validated) + the specific
statistical-unit gate. This is a Findings-tier-to-focused-Proceedings paper, not a
NeurIPS-novel-method paper.

---

## 6. Paper state (`paper/paper.tex`)

Compiles. Contains: abstract; intro (with a **health/clinical framing** paragraph
for ML4H — false senescence DE → misdirected senolytic targets, irreproducible
biomarkers); related work; methodology + **TikZ architecture figure** (`fig:arch`,
the two gates); results (Table 1 = 13-config sweep `tab:null`; FDR subsection;
wild-agent subsection `sec:wildagent` with CellAgent's 36; EviBound gate-passthrough
table `tab:evibound`; score robustness; **power preservation** Table 3 `tab:power`);
analysis; **limitations** (replicate counts, constructed-failure + CellAgent scope,
2-control-sample caveat, firewall scope, single signature); conclusion.
Authors: Rodela Ghosh, Aviral Gupta (USF). `custom.bib` author lists verified.

---

## 7. Remaining to-do (priority order)

1. **Results figure** — null-vs-real 2×2 bar chart (pgfplots, native). THE last
   content gap. Not done.
2. **Proofread pass** + check the compiled PDF renders tables/figure/refs.
3. **Save the CellAgent DE notebook** — the run that printed "36" is
   `analysis_20260705_083332.ipynb`; only step-1 notebooks got downloaded so far
   (`cellagent_analysis_step1.ipynb`). The "36" is verified in the pasted console
   output and recorded in `cellagent_evidence.md`, but the DE notebook artifact is
   not yet saved locally.
4. **Optional upside (weeks 3–6 before Sept):** second dataset / human cohort for
   generalizability; CellAgent fully-autonomous droplet run; **confounding** as a
   2nd demonstrated validity error (raises ceiling toward main-track "firewall
   governs a taxonomy" — but keep the pseudoreplication paper locked first).

---

## 8. Data & environment

- TMS FACS processed tissues in `backend/data/`: Kidney, Liver, Spleen, Aorta,
  Limb_Muscle (Lung excluded/unavailable).
- GSE226225 at `D:/validation_data/GSE226225.h5ad` (56,803 cells, human WI-38).
- `cellagent_null.h5ad` in `eval/results/ablation/` (105 cells, fenestrated, 4
  real 24-month male mice, random groupA/groupB split — a genuine null).
- `.env`: GEMINI keys, `GSE_DATA_DIR=D:/validation_data`, `GEMINI_MAX_RPM=0`.
- Windows console: prefix runs with `PYTHONIOENCODING=utf-8` (a `→` in
  `pipeline.py` prints crash cp1252 otherwise).

---

## 9. People / context

- **Rodela Ghosh** (user) — driving the research, first author. USF CS undergrad,
  Judy Genshaft Honors College. Goal: PhD in CS / AI-in-healthcare (CS-focused, no
  wet lab). `rg21@usf.edu`.
- **Aviral Gupta** — built the FastAPI backend; co-author. Project originated as a
  hackathon project (ended ~July 13).
- **Fei He** (USF; AI / Bioinformatics / Health Informatics; h-index ~20) —
  intended advisor for biology credibility + rec letter. Draft email exists to ask
  him to mentor toward the paper.
- **Guangjing Wang** (agentic AI systems) — intended second advisor for CS framing
  + rec letter; approach *after* Fei, once core is locked.
- Authorship: Rodela lead/first (drives research + writing); Aviral co-author
  (built backend). Settle explicitly before submission.

---

## 10. How to run key things

```powershell
# from repo root, with PYTHONIOENCODING=utf-8
$env:PYTHONIOENCODING="utf-8"
# Result 1 sweep:
.\backend\venv\Scripts\python.exe eval\ablation\null_harness\run_null_sweep.py --n-perm 200 --top 3
# Result 2:
.\backend\venv\Scripts\python.exe eval\ablation\power_preservation\power_preservation.py
# single null harness config:
.\backend\venv\Scripts\python.exe eval\ablation\null_harness\null_harness.py --cell-type "fenestrated cell" --n-perm 500
```
