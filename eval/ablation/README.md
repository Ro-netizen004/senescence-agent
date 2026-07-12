# Experiments (`eval/ablation/`)

Scripts are grouped by experiment. All write results to `eval/results/ablation/`.
Run from the **repo root** with the venv Python, e.g.:

```powershell
$env:PYTHONIOENCODING="utf-8"; .\backend\venv\Scripts\python.exe eval\ablation\null_harness\run_null_sweep.py
```

## `null_harness/` — Result 1: pseudoreplication false discovery
- `null_harness.py` — constructed-null experiment on one cell type: per-cell
  (ungoverned) vs pseudobulk (governed) DE, counts false-positive genes.
- `run_null_sweep.py` — runs `null_harness` across all TMS tissues × top cell
  types; writes `null_sweep_summary.csv/.md` (paper Table 1).

```
python eval/ablation/null_harness/run_null_sweep.py --n-perm 200 --top 3
```

## `agent_null_harness/` — Result 1b: null harness on the **real agent**
- `null_builder.py` — constructs fake 3m/24m nulls (homogeneous or random split).
- `agent_null_sweep.py` — runs `run_agent()` per permutation; scores DESeq2 +
  inference state (end-to-end, not isolated Wilcoxon/t-test).
- `run_agent_null_sweep.py` — multi-tissue sweep; writes `agent_null_sweep_summary_*.csv/.md`.

```
# Quick smoke (1 cell type, 3 permutations, governed — no Gemini needed):
python eval/ablation/agent_null_harness/agent_null_sweep.py --cell-type "fenestrated cell" --n-perm 3

# One cell type, paper-scale:
python eval/ablation/agent_null_harness/agent_null_sweep.py --cell-type "aortic endothelial cell" --n-perm 50

# All tissues (top 1 cell type each):
python eval/ablation/agent_null_harness/run_agent_null_sweep.py --n-perm 10 --top 1
```

## `power_preservation/` — Result 2: governance preserves power
- `power_preservation.py` — governed pseudobulk DE on GSE226225 (senescent vs
  control); shows it detects a real effect (7,613 genes, correct markers) vs
  ~0 on nulls. Writes `power_preservation.json`.

## `cellagent/` — "wild agent" evidence
- `make_cellagent_null.py` — builds `cellagent_null.h5ad` (stratified null) for
  the CellAgent experiment.
- `cellagent_colab.md` — Colab guide (see also `notebooks/cellagent_experiment.ipynb`).
- `run_ungoverned_agent.py` — our own ungoverned-agent ablation runner.
- Evidence lives in `eval/results/ablation/cellagent_evidence.md` + `cellagent_run_log.txt`.

## `transcripts/` — governed vs ungoverned narration
- `paired_transcripts.py` — same null prompt to the governed vs `AGENT_GOVERNANCE=off`
  agent; saves paired transcripts.

## `governance/` — component ablations
- `ablation_pseudorep.py`, `ablation_ism.py`, `ablation_router.py` — per-component
  ablations of the governance machinery.
- `run_all_ablations.py` — runs all three.

---
Note: scripts resolve the repo root via `Path(__file__).resolve().parents[3]`
(they live three directories below the root). Keep them at this depth or update
that line if you move them.
