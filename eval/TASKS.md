# Evaluation tasks — assign to teammates

Copy each block into GitHub Issues / Notion / Slack. Estimates assume kidney TMS dataset is uploaded.

---

## Task 1 — Dataset lock-in (Lead, 2 hours)

**Deliverables**

- [ ] Upload `tabula-muris-senis-...-Kidney.h5ad` (or project h5ad).
- [ ] Fill `eval/dataset_manifest.yaml` with `file_id`, `species`, cell count.
- [ ] Run one chat: T cell p-value 3m vs 24m; save full JSON response as `eval/fixtures/tcell_pvalue_run.json`.

**Acceptance:** Manifest committed; fixture JSON attached.

---

## Task 2 — Gold case expansion (Teammate, 1–2 days)

**Deliverables**

- [ ] Review `eval/gold_cases.yaml` (starter 24 cases).
- [ ] Add **6+ new cases** (your ideas: DESeq2 cell types, wrong cell name, global vs cell-type age).
- [ ] For each case, run `/chat` once; fill `eval/results/case_log.csv`:

  Columns: `case_id, tools_called, state, p_value_if_any, pass_tool_gold (y/n), pass_state_gold (y/n), notes`

**Acceptance:** ≥30 rows in `case_log.csv`; notes for every failure.

**Starter prompts to add**

1. "Run DESeq2 on mesangial cells, 3m vs 24m."
2. "Which cluster has the highest senescence score?"
3. "Compare senescence between 3m and 24m across all cells" (trap: global descriptive).
4. "Is senescence significantly higher in macrophages at 24m?" (needs `test_senescence_difference`).
5. "p-value for neurons" (trap: cell type not in kidney).
6. "Run everything and tell me what's interesting" (panel path).

---

## Task 3 — Layer 1 pytest fixtures (Teammate, 1 day)

**Deliverables**

- [ ] Create `eval/fixtures/tcell_test_result.json` from real `test_senescence_difference` output.
- [ ] Create `eval/fixtures/compare_age_descriptive.json` from `compare_across_age`.
- [ ] Implement `backend/tests/test_validation_layer.py`:
  - `assign_inference_state` → `LOW_POWER` for T cell fixture
  - `assign_inference_state` → `DESCRIPTIVE_ONLY` for compare_age fixture
  - `render_strict_output` → no substring `statistically significant` for LOW_POWER fixture

**Acceptance:** `pytest backend/tests/test_validation_layer.py -q` green without `GEMINI_API_KEY`.

---

## Task 4 — Claim linter (Teammate, 2 days)

**Deliverables**

- [ ] Finish `eval/claim_linter.py` (extend stub).
- [ ] Input: `{ reply, tool_calls, gold_case }` → `{ violations: [] }`.
- [ ] Rules at minimum:
  - If gold `forbid_significance_claim`: flag `significant`, `proves`, `confirms increase`
  - If tool state `LOW_POWER` or `NOT_SIGNIFICANT`: flag significance claims
  - If only `compare_across_age`: flag `p-value` / `p =` in reply
  - If gold `require_p_value_in_reply`: must match tool JSON p within 0.02
- [ ] Run on `case_log.csv` → `claim_audit.csv`

**Acceptance:** README section in `eval/README.md` with example command; audit CSV committed.

---

## Task 5 — Tool routing scorecard (Teammate, 1 day)

**Deliverables**

- [ ] Subset: all cases tagged `category: pvalue` (8 cases).
- [ ] Run each **3 times** (Gemini variance).
- [ ] Score: `% with test_senescence_difference in tool_calls`.

**Acceptance:** `eval/results/routing_pvalue.csv` + 1 paragraph summary for paper.

---

## Task 6 — Reference numbers script (Teammate, 1 day)

**Deliverables**

- [ ] Script `eval/compute_reference_values.py`:
  - Loads h5ad by `file_id`
  - Runs `test_senescence_difference` T cell 3m vs 24m
  - Writes `eval/reference_values.json` (p, medians, n_samples, n_cells)
- [ ] Document command in `eval/README.md`

**Acceptance:** JSON committed; values match manual chat within tolerance.

---

## Task 7 — Human evaluation (Teammate, 3 days, optional)

**Deliverables**

- [ ] Pick **10 cases** (5 p-value traps, 5 descriptive).
- [ ] Collect replies: full system only (first pass).
- [ ] 3 raters complete `human_rubric.md` form.

**Acceptance:** `eval/results/human_scores.csv` + mean overstatement score.

---

## Task 8 — Baseline comparison (Lead + dev, 1 day)

**Deliverables**

- [ ] Implement `USE_DETERMINISTIC_REPLY=0` branch in `agent.py` (return Gemini text when tools ran).
- [ ] Re-run 20 gold cases × 2 modes.
- [ ] Table: forbidden-claim rate, tool accuracy (both modes).

**Acceptance:** `eval/results/baseline_comparison.md` with numbers.

---

## Suggested split (team of 3)

| Person | Tasks |
|--------|--------|
| **You** | Task 1, Task 8, paper figures |
| **Teammate A** | Task 3, Task 6 |
| **Teammate B** | Task 2, Task 5 |
| **Teammate C** | Task 4 (+ Task 7 if time) |

---

## Week 1 calendar

| Day | Focus |
|-----|--------|
| Mon | Task 1 + everyone reads `docs/senescence_agent_architecture.md` |
| Tue–Wed | Task 2 + Task 6 in parallel |
| Thu | Task 3 + Task 4 start |
| Fri | Task 4 finish; first `claim_audit.csv`; sync meeting |
