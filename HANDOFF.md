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
  `agent/tool_router.py`. **A sample only counts as a replicate if it has ≥
  `MIN_CELLS_PER_SAMPLE` (=20) cells of the queried cell type** — 1–3-cell
  "replicates" are excluded (added 2026-07-12; see §7 changelog). The threshold is
  a single source of truth in `tools/build_pseudobulk.py`, imported by both the
  gate and the null harness so they can never drift.
- **Gate 2 — Justification** (`agent/inference_state.py`): post-execution.
  Five-state machine (DESCRIPTIVE_ONLY, LOW_POWER, NOT_SIGNIFICANT,
  SIGNIFICANT_INFERENTIAL, BLOCKED) + `validity_flags` (cell_unit_not_inferential,
  circular_inference_risk, uncorrected_multiple_testing, **technical_artifact_risk**)
  that **override** significance — an inadmissible result cannot conclude even with
  a small p. `technical_artifact_risk` fires when the result-plausibility check
  (`tools/run_deseq2.assess_de_plausibility`) returns `verdict="suspect"`
  (implausible fold-changes / near-uniform direction), downgrading the state to
  DESCRIPTIVE_ONLY so an artifact result is never reported as a finding.
- **Deterministic renderer** (`agent/output_renderer.py`): no LLM prose for
  results; "interpretation firewall".
- **Governance toggle** (`agent/governance.py`): `AGENT_GOVERNANCE=off` enables the
  ungoverned ablation — per-cell tools (`tools/percell_inference.py`), no gates,
  LLM narration. Production always governed.
- **Rate limiter** (`agent/rate_limit.py`): `GEMINI_MAX_RPM` (currently 0 = off in
  `.env`; user is on paid Gemini tier, ~1000 RPM).
- Tools: `tools/senescence.py` (SenMayo scoring; NOTE the `use_raw=False` fix),
  `tools/statistics.py` (per-sample Mann-Whitney), `tools/run_deseq2.py`
  (pseudobulk DESeq2 + `assess_de_plausibility` result-artifact check) +
  `tools/build_pseudobulk.py` (pseudobulk; extracts raw integer counts from
  `adata.raw.X`, drops sub-`MIN_CELLS_PER_SAMPLE` samples), `tools/age_analysis.py`.
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

## 7. Changelog & remaining to-do

### Recent changes — 2026-07-12 (two firewall fixes)

Triggered by a real agent output: TMS `mesangial cell` 24m-vs-3m DESeq2 returned
**814 "significant" genes with a badge of SIGNIFICANT_INFERENTIAL**, while the
plausibility warning underneath said the numbers were a technical artifact (median
|log2FC|≈10, 93% one direction, several genes at the −43.28 bound). Investigation
(NOT a counts bug — `adata.raw.X` is real integer counts, verified) traced it to an
extremely rare cell type: 93 cells total, pseudobulk "replicates" built from as few
as **1 cell**, and a ~3.8× library-size imbalance between age groups.

- **Fix B — admissibility min-cells gate (root cause).** `build_pseudobulk_matrix`
  now drops samples with `< MIN_CELLS_PER_SAMPLE` (=20) cells; `admissibility.py`
  counts only such samples as replicates and blocks when a group falls below 2.
  Production now matches the null harness (which always used 20). Constant is the
  single source of truth in `tools/build_pseudobulk.py`, imported by
  `null_harness.py`. Result: the mesangial contrast is now **BLOCKED** up front;
  abundant types (e.g. `fenestrated cell`) stay admissible. Gate and tool keep the
  exact same replicate set (no drift, verified).
- **Fix A — plausibility governs the state (the overclaim itself).** A
  `verdict="suspect"` plausibility result now emits the `technical_artifact_risk`
  validity flag and downgrades the state from SIGNIFICANT_INFERENTIAL to
  DESCRIPTIVE_ONLY (`conclusion=None`, `validity_gate_passed=False`); the renderer
  reports the genes as "exploratory only, not a valid finding". Previously the
  warning was advisory prose bolted above a SIGNIFICANT_INFERENTIAL badge.
- Files: `backend/tools/build_pseudobulk.py`, `backend/agent/admissibility.py`,
  `backend/agent/inference_state.py`, `backend/agent/output_renderer.py`,
  `eval/ablation/null_harness/null_harness.py`. Tests added in
  `backend/tests/test_inference_state.py` (3 new); full suite 31/31 green.
- **Paper implication:** the firewall now demonstrably governs **three** validity
  errors — pseudoreplication, insufficient/unreliable replicates (min-cells), and
  technical-artifact results — not one. Strengthens the "governs a taxonomy" framing.

### Recent changes — 2026-07-12 (agent-level null validation + paper edits)

Same session, follow-on work.

- **Agent-level null harness run on the REAL agent** (`eval/ablation/agent_null_harness/`,
  which drives `run_agent` end-to-end: routing → admissibility → DESeq2 → inference
  state, unlike the method-level `null_harness.py`). Governed arm, constructed nulls
  (truth = 0). Two regimes:
  - **2v2 (Kidney `fenestrated cell`, homogeneous 24m/male stratum, 3 perms):**
    inferential FDR **0%**; but DESeq2 emits ~**400 raw FP genes/perm**, caught by the
    **power gate** (`LOW_POWER` → exploratory). Note DESeq2 is anti-conservative at
    n=2 (400 FPs) vs the method-level pseudobulk **t-test** (0.47 in Table 1) — the
    Table 1 "0.47 governed" is the t-test proxy, NOT the agent's DESeq2. Agent yields
    **0 false conclusions**, not ~0 raw genes.
  - **6v6 (Spleen `B cell`, random-mode null, 5 perms):** inferential FDR **0%**;
    ~33–74 raw FP genes/perm. Here the power gate is SILENT (6 reps/group), so the
    **plausibility gate (Fix A)** does all the work → `DESCRIPTIVE_ONLY`. Deterministic
    counterfactual: **without Fix A this is 5/5 `SIGNIFICANT_INFERENTIAL` = 100%
    inferential FDR**; with it, 0%. Fix A is load-bearing at adequate power.
  - **Defense-in-depth confirmed:** low power → power axis catches nulls; adequate
    power → plausibility axis catches nulls. Neither alone spans both; together 0%
    inferential FDR across the power range. Results: `agent_null_Kidney_fenestrated_cell_governed.json`,
    `agent_null_Spleen_b_cell_governed.json`.
- **CRITICAL coupling (shrinkage ↔ plausibility).** The 6v6 firewall success relies
  on TMS unshrunk DESeq2 giving null genes *large* LFCs (which trip plausibility).
  **Naive LFC shrinkage would collapse those magnitudes → plausibility passes → the
  6v6 nulls flip to `SIGNIFICANT_INFERENTIAL` = real false discoveries.** So shrinkage
  is NOT a free best-practice add: it must be paired with plausibility-threshold
  recalibration (validate against shrunk null vs shrunk GSE226225). Deferred, not done.
  Empirical basis: proximal-tubule 24m-vs-18m shrinkage test (median |log2FC| 8.2→1.6).
- **Paper edits (`paper/paper.tex`).** Reconciled the power-preservation framing with
  the agent's own `LOW_POWER` verdict on the 2-control GSE226225 design (the agent
  would stamp the flagship 7,613-gene result `LOW_POWER`, not a licensed conclusion).
  Three edits: (1) §Governance Preserves Power — reframed "power preservation" as a
  property of the statistical *unit* (sensitivity) vs inferential *licensing*;
  (2) §Why Governance Does Not Over-Refuse — clarified restraint targets the claim,
  not the data (surfaces genes under `DESCRIPTIVE_ONLY`); (3) §Limitations power cohort
  — added explicit disclosure that the agent reports this contrast `LOW_POWER`.
  **Not yet recompiled** — no LaTeX toolchain on this machine (pdflatex/latexmk absent);
  verify the PDF elsewhere.

### Remaining to-do (priority order)

1. **Results figure** — null-vs-real 2×2 bar chart (pgfplots, native). THE last
   content gap. Not done.
2. **Proofread pass** + check the compiled PDF renders tables/figure/refs.
3. **Save the CellAgent DE notebook** — the run that printed "36" is
   `analysis_20260705_083332.ipynb`; only step-1 notebooks got downloaded so far
   (`cellagent_analysis_step1.ipynb`). The "36" is verified in the pasted console
   output and recorded in `cellagent_evidence.md`, but the DE notebook artifact is
   not yet saved locally.
4. **Recompile the paper** on a machine with LaTeX and verify the three
   power-preservation edits render + read cleanly (this machine has no toolchain).
5. **Shrinkage decision (deferred, coupled).** IF adding LFC shrinkage to
   `tools/run_deseq2.py` (best practice; recommended by the plausibility warning
   itself), it MUST be paired with plausibility-threshold recalibration, or it
   breaks the 6v6 firewall (see coupling note above). Recalibrate magnitude
   thresholds (`_IMPLAUSIBLE_MEDIAN_LFC`, `_EXTREME_LFC`, `_EXTREME_FRAC_WARN`)
   against shrunk-null vs shrunk-GSE226225; keep `_DIRECTION_SKEW_WARN` (shrinkage-
   robust). Note `power_preservation.py` has its OWN inlined DESeq2 — changing the
   agent tool does not touch that paper number.
6. **Optional upside (weeks 3–6 before Sept):** second dataset / human cohort for
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
