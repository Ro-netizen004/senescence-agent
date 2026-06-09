# Senescence-Agent Evaluation Pack

Starter kit for thesis / methods paper evaluation. Work in **layers** (fast → slow).

## Prerequisites

1. Kidney Tabula Muris Senis `.h5ad` in `backend/data/` (or upload once via UI; note `file_id`).
2. Backend running with `GEMINI_API_KEY` in repo-root `.env`.
3. Python: use `backend/venv`.

```powershell
cd backend
.\venv\Scripts\activate
cd ..
```

Record your `file_id` after upload in `eval/dataset_manifest.yaml`.

---

## Layer 1 — Validation unit tests (no Gemini, ~1 day)

**Owner:** Teammate A  
**Goal:** Prove `inference_state` + renderer match gold on **fixed JSON fixtures**.

- [ ] Copy real tool outputs into `eval/fixtures/` (from one manual run).
- [ ] Add `backend/tests/test_validation_layer.py` (pytest).
- [ ] CI-safe: no API key required.

**Done when:** `pytest backend/tests/test_validation_layer.py` passes.

---

## Layer 2 — Gold benchmark cases (~2 days)

**Owner:** Teammate B  
**Goal:** Fill and run `eval/gold_cases.yaml` (30+ prompts).

- [ ] Complete `dataset_manifest.yaml` with `file_id` + species.
- [ ] Run each case via `/chat` or `run_agent`; log to `eval/results/manual_run_TEMPLATE.jsonl`.
- [ ] Mark `status: verified | needs_review` per case.

**Done when:** ≥30 cases verified; spreadsheet or JSONL complete.

---

## Layer 3 — Claim linter (~2 days)

**Owner:** Teammate C  
**Goal:** `eval/claim_linter.py` scores replies vs gold rules.

- [ ] Implement forbidden / required regex checks.
- [ ] Run on JSONL from Layer 2 → `eval/results/claim_audit.csv`.

**Done when:** summary row: `% cases with 0 violations` for full system.

---

## Layer 4 — Baseline ablation (~1 day, needs dev)

**Owner:** You (or dev teammate)  
**Goal:** Compare full system vs “Gemini prose after tools”.

- [ ] Add env flag `USE_LLM_REPLY=1` in `agent.py` (optional; see TASKS.md).
- [ ] Re-run subset of gold cases (10 p-value traps + 10 descriptive).

**Done when:** table: forbidden-claim rate B0 vs B1.

---

## Layer 5 — Human rubric (optional, ~3 days)

**Owner:** Teammate D  
**Goal:** 5 raters × 10 prompts × 2 conditions.

- [ ] Use `eval/human_rubric.md`.
- [ ] Collect Google Form / spreadsheet.

---

## Run the 20 gold cases (recommended)

**1. Prerequisites**

```powershell
pip install pyyaml
```

Fill `eval/dataset_manifest.yaml`:

```yaml
file_id: "your-uuid-from-upload"
species: mouse
```

Backend uses repo-root `.env` with `GEMINI_API_KEY`. Start from repo root or `backend/`.

**2. Dry-run (no API — lists cases)**

```powershell
cd backend
.\venv\Scripts\python.exe ..\eval\run_gold_cases.py --day1 --dry-run
```

**3. Run Day 1 batch (20 Gemini calls)**

Skips `panel_run_everything` (0 API) and `multistep_score_then_test` (save for day 2).

```powershell
.\venv\Scripts\python.exe ..\eval\run_gold_cases.py --day1 --output ..\eval\results\day1\day1.jsonl
```

**4. Panel without API (optional same session)**

```powershell
.\venv\Scripts\python.exe ..\eval\run_gold_cases.py --id panel_run_everything --output ..\eval\results\day1\day1.jsonl
```

**5. Audit replies**

```powershell
cd ..
python eval/claim_linter.py eval/results/day1/day1.jsonl
# also writes eval/results/day1/day1_linter.txt (or use --output path)
```

**Other options**

```powershell
.\venv\Scripts\python.exe ..\eval\run_gold_cases.py --all --output ..\eval\results\full_run.jsonl
.\venv\Scripts\python.exe ..\eval\run_gold_cases.py --id pvalue_tcell_3m_24m
```

## Quick single-case test

```powershell
cd backend
.\venv\Scripts\python.exe -c "
from agent.agent import run_agent
r = run_agent([], 'What is the p-value for senescence in T cells at 3m vs 24m?', 'YOUR_FILE_ID', 'mouse')
print(r['reply'][:800])
print('tools:', [t['name'] for t in r['tool_calls']])
"
```

Replace `YOUR_FILE_ID` after upload.

---

## Files in this folder

| File | Purpose |
|------|---------|
| `gold_cases.yaml` | Benchmark prompts + expected tools/states |
| `dataset_manifest.yaml` | file_id(s) for eval datasets |
| `TASKS.md` | Assignable teammate tickets |
| `human_rubric.md` | 5-question survey for raters |
| `claim_linter.py` | Automated reply audit; writes `<stem>_linter.txt` by default |
| `fixtures/` | Frozen tool JSON for Layer 1 |

See **TASKS.md** for copy-paste assignments.
