# Senescence Agent — Complete Project Briefing

*One-document reference: biology → statistics → architecture → code → validation →
positioning → honest points. Written for the paper, Q&A prep, and onboarding.*

**Core principle:** the LLM only ever *proposes* (routing/intent). Every statistic,
every claim-permission, and all user-facing prose are **deterministic**. Three
validation tests show the system is *silent on nulls, sensitive on real signal, and
honest at the conclusion*.

**One-line flow:**
`/chat → cache + pipeline → Tier 1/2/3 routing → Gate 1 (admissibility, pre-exec) →
deterministic tool (pseudobulk / per-sample) → Gate 2 (inference state + validity
flags, post-exec) → deterministic renderer`

**Contents**
1. Biology
2. The statistical problem
3. The system (architecture, conceptual)
4. The Scanpy tool layer
5. Code walkthrough (end to end)
6. Validation (three tests, with code)
7. Positioning & contribution
8. The subtle / honest points
9. Appendix: key files, numbers, constants

---

# 1. BIOLOGY

**Senescent cells** = cells that have **permanently stopped dividing but won't die**
("zombie cells"). A stress response: when a cell has damage it can't safely repair,
it locks into permanent arrest instead of dividing (an anti-cancer brake). Triggered
by DNA damage, telomere shortening, oncogenes, oxidative stress, aging.

**Why they matter (clinical / ML4H framing):** they **accumulate with age**, and
their secretions (the **SASP** — senescence-associated secretory phenotype) cause
chronic inflammation that drives arthritis, fibrosis, frailty, and age-related
disease. Major drug target: **senolytics** kill them selectively. *A false senescence
gene misdirects the search for those drug targets.* That's the stakes.

**The four hallmarks — and exactly what the agent detects:**

| Hallmark | Genes (direction in senescent) |
|---|---|
| Permanent cell-cycle arrest | **MKI67, BIRC5, CENPF, PRC1, TOP2A, CCNB1, CDK1 ↓** |
| Arrest enforcers | **p16 (CDKN2A), p21 (CDKN1A) ↑** |
| SASP (inflammatory secretion) | **IL6, MMP3, GDF15 ↑** |
| Nuclear lamina breakdown | **LMNB1 (lamin B1) ↓** — canonical |

**Key nuance:** in etoposide senescence the **down/proliferation signal dominates**
(huge, coherent, −5 to −8 log2FC). The **up SASP/arrest markers are real but modest**
(+1.6 to +3.5), so they rank *lower* by p-value — not the top-labeled volcano genes.

**SenMayo** = the senescence gene signature scored per cell (~120–125 genes; Saul et
al. 2022), via `sc.tl.score_genes`.

**Datasets:**
- **Tabula Muris Senis (TMS) FACS** — mouse aging atlas (Kidney, Liver, Spleen, Aorta,
  Limb_Muscle). Smart-seq2, deep per-cell, **few mice per group**. The **null**
  dataset. Ages 3m/18m/24m + `mouse.id`.
- **GSE226225** — human WI-38 fibroblasts, **etoposide-induced** senescence, ~56,803
  cells. The **real-effect / power** dataset.

**Etoposide (ETO)** = a **chemotherapy drug** (topoisomerase II inhibitor) that causes
**DNA double-strand breaks** → DNA-damage response → senescence. **Not radiation**
(though radiation induces senescence by the same DNA-damage mechanism).

---

# 2. THE STATISTICAL PROBLEM (the crux)

**Pseudoreplication** (Squair et al. 2021, Nat Commun): treating measurements that
aren't independent as if they are. Cells within one mouse are correlated. A per-cell
test with thousands of cells has enormous *apparent* n → tiny p-values → massive false
positives, because the real n is the number of **animals**, not cells.

**The statistical unit is the fix.** The correct unit for a between-group biological
comparison is the **biological replicate (animal/donor)**, not the cell.

**Why FDR correction does NOT fix it:** FDR controls false positives *given* valid
independent tests. If the *unit* is wrong, every gene's p-value is anti-conservative,
so FDR just scales garbage (proximal tubule ~1,650 raw → ~916 after FDR per-cell;
pseudobulk ~0). **The fix is the unit, not the correction.**

**Pseudobulk** = sum raw counts of all cells per sample → one profile per replicate →
standard bulk DE (DESeq2) across replicates.

**Constructed null (Squair method):** randomly assign *whole mice* to two fake groups
within one cell type. Truth = **0** DE genes; every reported gene is a false positive.

**Two DESeq2 failure modes you must know:**
1. **Anti-conservative at low n.** At 2 samples/group its dispersion estimate is
   unstable → inflated false positives even on pseudobulk (agent null at 2v2 gave
   ~400 raw genes vs the t-test's 0.47).
2. **Unshrunk fold-changes blow up for low-count genes.** DESeq2 reports MLE log2FC
   by default; on sparse data these hit ±10 to ±43. **LFC shrinkage** (apeglm) fixes
   the bulk (proximal tubule: median |LFC| 8.2 → 1.6) — but see the coupling caveat
   in §8.

---

# 3. THE SYSTEM (architecture, conceptual)

**Governed single-LLM agent** (NOT multi-agent). The LLM only *proposes*; statistics,
permission, and prose are deterministic.

**Three-tier routing** ("trust the LLM as little as possible"):
1. **Tier 1** — deterministic keyword router, no LLM.
2. **Tier 2** — LLM emits a schema-constrained **JSON intent** (workflow + cell type +
   ages), a deterministic validator checks it **against the real dataset** and rejects
   anything invented.
3. **Tier 3** — open-ended Gemini tool-calling fallback. Even here, tools are gated and
   the reply is deterministically rendered.

**Gate 1 — Admissibility (before the tool runs).** Refuses inadmissible designs: no
replicate column, **< 2 usable replicates/group** (a sample needs **≥20 cells**),
confounded contrast, circular (cluster-defined) DE. Invalid claim is *never computed*.

**Gate 2 — Justification (after).** Five states — **DESCRIPTIVE_ONLY, LOW_POWER,
NOT_SIGNIFICANT, SIGNIFICANT_INFERENTIAL, BLOCKED** — plus **validity flags** that
*override* significance: `cell_unit_not_inferential`, `circular_inference_risk`,
`uncorrected_multiple_testing`, `technical_artifact_risk`. A small p-value alone never
earns a conclusion.

**Deterministic renderer** — user-facing text built from structured facts + state,
never LLM prose on conclusions.

**Column-roles / `dataset_profile`** — single source of truth (sample/age/cell-type
columns); editable via the "Dataset setup" UI; every tool + gate reads it.

**Governance toggle** — `AGENT_GOVERNANCE=off` = ungoverned ablation (per-cell tools,
no gates, LLM narrates). The arm that produces the false discoveries.

---

# 4. THE SCANPY TOOL LAYER

## Agent-callable tools (the `tool_map`)

| Tool | Underlying Scanpy/stats | Statistical unit | Governance role |
|---|---|---|---|
| `generate_umap` | `sc.tl.umap` + `sc.pl.umap` | cell | Descriptive (viz) |
| `find_senescence_markers` | SenMayo coverage | — | Descriptive |
| `senescence_score` | `sc.tl.score_genes` (SenMayo), per Leiden cluster | cell | Descriptive |
| `get_cluster_annotations` | cell-type label per cluster | cell | Descriptive |
| `compare_across_age` | senescence score by age | cell | Descriptive (cannot be inferential) |
| `test_senescence_difference` | **per-sample** `mannwhitneyu` on SenMayo medians | **replicate** | Inferential, **governed** |
| `run_deseq2` | pseudobulk → `DeseqDataSet`/`DeseqStats` + plausibility + volcano | **replicate** | Inferential, **governed** |

**The split that matters:** five descriptive tools operate per cell but *never make an
inferential claim*. Only the **two inferential tools** aggregate to the **replicate**
and are wrapped by the admissibility gate — correct-unit-by-design.

## Pipeline / preprocessing (`preprocessing.py`, `clustering.py`)

| Function | Scanpy calls |
|---|---|
| `quality_control` | `sc.pp.filter_cells(min_genes=200)`, `filter_genes(min_cells=3)`, mito QC |
| `normalize` | `sc.pp.normalize_total(1e4)` → `sc.pp.log1p` |
| `lock_raw_counts` | integer counts → `layers['counts']` (for DESeq2) |
| `cluster_cells` | `highly_variable_genes` → `sc.pp.pca` → `sc.pp.neighbors` → `sc.tl.leiden` |
| `annotate_clusters_by_markers` | `sc.tl.rank_genes_groups(leiden, "wilcoxon")` → curated markers |

*(On pre-processed atlases like TMS, QC/normalize/cluster are **skipped** — authors'
Leiden + normalization reused.)*

## Circular / descriptive-only, and ungoverned ablation

| Tool | Note |
|---|---|
| `differential_expression` | `rank_genes_groups` per Leiden cluster — **circular** (clusters defined on the same expression) → descriptive only |
| `differential_expression_percell` | per-**cell** `mannwhitneyu` DE — **pseudoreplication** (ablation only) |
| `test_senescence_difference_percell` | per-**cell** `mannwhitneyu` on scores — same failure (ablation only) |

## Utilities
`build_pseudobulk_matrix` (min-cells + raw-count sum) · `assess_de_plausibility` +
`generate_volcano` · `resolve_cell_type` (fuzzy match) · `normalize_gene_names` ·
`build_dataset_summary` · `load_senmayo_genes`.

---

# 5. CODE WALKTHROUGH (end to end)

## 5.1 Entry point → data preparation

`POST /chat` (`main.py`) calls `run_agent`. Dataset loaded once, cached, run through a
deterministic Scanpy pipeline.

```python
# agent/agent.py — run_agent
adata = get_adata(file_id)                 # in-memory cache (TTL 1h, max 3)
if adata is None:
    adata = sc.read_h5ad(resolve_dataset_path(file_id))
    cache_adata(file_id, adata)
ensure_pipeline(adata, species)            # QC / normalize / cluster, idempotent
governed = governance_enabled()            # production = True always
```

`ensure_pipeline` **locks raw integer counts** into `layers['counts']` — DESeq2 must
see counts, never normalized values:

```python
# agent/pipeline.py — ensure_pipeline (condensed)
already_normalized = adata.raw is not None          # pre-processed atlas?
if "counts" not in adata.layers:
    if already_normalized:
        adata.layers["counts"] = adata.raw.X[:, raw_idx]   # counts live in .raw
    else:
        adata.layers["counts"] = adata.X.copy()
# QC / normalization SKIPPED when already pre-processed (avoids double-normalizing)
if "dataset_profile" not in adata.uns:
    adata.uns["dataset_profile"] = _infer_dataset_profile(adata, species)
```

The `dataset_profile` (sample/replicate column, age/group column, cell-type column) is
the single source of truth every downstream component reads.

## 5.2 Three-tier routing

```python
# agent/agent.py — run_agent (governed path)
if governed:
    # ── Tier 1: deterministic keyword router (NO LLM) ──
    decision = route(message, adata)
    if decision.concept_reply:
        return {"reply": decision.concept_reply, ...}
    if decision.workflow_id in WORKFLOWS:
        return _run_workflow_from_route(decision, tool_map, message)

    # ── Tier 2: LLM structured-intent + deterministic validation ──
    intent = extract_intent(message, adata)          # LLM → JSON
    routed = validate_and_route(intent, adata)        # checked vs real dataset
    if routed is not None and routed.workflow_id in WORKFLOWS:
        return _run_workflow_from_route(routed, tool_map, message)

# ── Tier 3: Gemini tool-calling fallback (loop below) ──
```

**Tier 1** — pure string matching:

```python
# agent/intent_router.py — route()
if _wants_analysis_panel(message):                  # "run a full analysis", …
    return RouteDecision(workflow_id="panel")
if _wants_deseq2(message):
    parsed = _parse_deseq2_template(message, adata, profile)   # regex over real cols
    if parsed:
        return RouteDecision(workflow_id="deseq2", tool_args={"run_deseq2": {...}})
```

**Tier 2** — LLM proposes a schema-constrained intent; validator confirms it against
the real data and **rejects anything invented**:

```python
# agent/intent_extractor.py
def validate_and_route(intent, adata):
    workflow = str(intent.get("workflow") or "")
    if workflow not in _ROUTABLE_WORKFLOWS: return None
    if workflow in _CONTRAST_WORKFLOWS:
        resolved_ct = _resolve_cell_type(intent.get("cell_type"),
                                         _available_cell_types(adata))
        if not resolved_ct: return None          # cell type not in dataset → reject
        # ages validated against profile["age_values"], else fall back to extremes
    return RouteDecision(workflow_id=workflow, tool_args={...})
```

**Tier 3** — classic tool-calling loop; even here tools are governed and the reply is
deterministic:

```python
# agent/agent.py — Tier 3 loop
model = genai.GenerativeModel(model_name=MODEL, tools=TOOLS, ...)
chat = model.start_chat(history=...)
for i in range(max_iterations):
    response = chat.send_message(current_message)
    # ... execute any function_call via tool_map (Gate 1 still wraps it) ...
    if not tool_call_parts:               # model produced its final answer
        return {"reply": _deterministic_reply(tool_calls_log), ...}  # NOT the LLM's prose
```

## 5.3 Gate 1 — Admissibility (before the tool runs)

```python
# agent/tool_router.py — build_tool_map
def _gate(tool_name, fn):
    if not governed:            # ablation → no gate
        return fn
    def gated(args):
        adm = check_admissibility(tool_name, args or {}, adata)
        if not adm["admissible"]:
            return admissibility_block_result(tool_name, adm)   # BLOCKED, no p-value
        result = fn(args)
        if adm.get("warnings"):
            result.setdefault("admissibility_warnings", []).extend(adm["warnings"])
        return result
    return gated

"run_deseq2": _gate("run_deseq2", _deseq2_impl),
"test_senescence_difference": _gate("test_senescence_difference", _test_impl),
```

```python
# agent/admissibility.py — a sample counts as a replicate only with ≥ MIN_CELLS_PER_SAMPLE (=20)
reps, excluded = _replicates_per_group(scoped, sample_col, group_col, groups,
                                       MIN_CELLS_PER_SAMPLE)
low = [g for g, n in reps.items() if n < MIN_ADMISSIBLE_REPLICATES]   # < 2
if low:
    reasons.append("insufficient_replicates: … a per-cell test would be pseudoreplication.")
confounders = _confounded_with(scoped, sample_col, group_col, groups)  # perfect separation
```

Refuses: **no replicate column, < 2 usable replicates/group, confounded contrast,
circular DE.** `MIN_CELLS_PER_SAMPLE` is shared with the null harness so production and
evaluation never drift.

## 5.4 The tools (deterministic statistical core)

```python
# tools/build_pseudobulk.py — sum RAW counts per sample; drop tiny samples
usable_samples = set(sample_sizes[sample_sizes >= MIN_CELLS_PER_SAMPLE].index)
for sample in ad.obs[sample_column].unique():
    if sample not in usable_samples:           # <20 cells → not a real replicate
        continue
    bulk = X[idx].sum(axis=0).astype(int)      # integer counts for DESeq2
```

```python
# tools/run_deseq2.py — plausibility fingerprint of a technical artifact
def assess_de_plausibility(results_df):
    sig = results_df[results_df["padj"] < 0.05]
    median_abs = sig["log2FoldChange"].abs().median()
    skew = max((sig.log2FoldChange>0).sum(), (sig.log2FoldChange<0).sum())/len(sig)
    if median_abs > 5.0:  reasons.append("|log2FC| implausibly large …")   # ~32-fold
    if skew > 0.90:       reasons.append("near-uniform direction → library-size artifact")
    return {"verdict": "suspect" if reasons else "ok", "reasons": reasons, ...}
```

```python
# tools/run_deseq2.py — the governed DESeq2 itself
c = count_df.loc[:, count_df.sum(axis=0) >= 10]        # drop all-zero genes
dds = DeseqDataSet(counts=c, metadata=meta_df, design_factors="_group")
dds.deseq2()
stat_res = DeseqStats(dds, contrast=["_group", comp_label, ref_label])
stat_res.summary()
```

`test_senescence_difference` does the same at the score level: it tests **per-sample
medians** (Mann-Whitney), never per-cell values.

## 5.5 Gate 2 — Justification (after the tool runs)

Gate 2 decides **how much you're allowed to claim** from a result — from "just
describe the numbers" up to "yes, this is a real finding." It works along **two
independent axes, and both must pass before a conclusion is licensed.**

**Axis 1 — the five states (power / significance).** *Did the test run, was it
powered, was it significant?* (assigned in this order for `run_deseq2`):

| State | When | Permits |
|---|---|---|
| **BLOCKED** | Gate 1 refused it, or the tool errored | nothing (no result) |
| **NOT_SIGNIFICANT** | ran, powered, but **0 genes** pass FDR | "no significant difference" (≠ absence proof) |
| **LOW_POWER** | ran, but **< 3 replicates/group** | numeric facts only — *exploratory*, even if "significant" |
| **DESCRIPTIVE_ONLY** | a descriptive tool, **or** an inferential result knocked down by a validity flag | numeric facts, **no conclusion / no narrative** |
| **SIGNIFICANT_INFERENTIAL** | ran, powered, significant, **and no validity flags** | the **only** state that licenses a conclusion |

**Axis 2 — the four validity flags (is the inference even valid?).** Reasons a claim
is invalid *regardless of the p-value*:

| Flag | Meaning |
|---|---|
| `cell_unit_not_inferential` | test used the **cell** as the unit → **pseudoreplication** |
| `circular_inference_risk` | groups **defined from the same expression** tested (clusters → marker DE) → **double-dipping** |
| `uncorrected_multiple_testing` | many per-gene p-values with **no adjusted p** |
| `technical_artifact_risk` | effect sizes look like a **technical artifact**, not biology |

**The override (heart of Gate 2):** any validity flag **wins** over a licensing state —
the *validity axis overrides the power axis*. To conclude you need **both**: state =
`SIGNIFICANT_INFERENTIAL` **and** zero validity flags.

```python
# agent/agent.py — _execute_tool
result = tool_map[name](args)
if governed and isinstance(result, dict):
    result = apply_inference_state(name, result, args)   # attaches inference_state block
```

```python
# agent/inference_state.py — assign_inference_state (run_deseq2 branch)
if not n_sig:            return NOT_SIGNIFICANT
if low_power:            return LOW_POWER               # < 3 replicates/group
if _plausibility_suspect(result):                       # Gate-2 artifact check
    return DESCRIPTIVE_ONLY                             # significant but not a valid finding
return SIGNIFICANT_INFERENTIAL

# build_state_record — makes "small p-value alone" insufficient
if record["validity_flags"] and level == INFERENTIAL:
    record["allowed_interpretation_level"] = "DESCRIPTIVE_ONLY"
    record["conclusion"] = None
    record["validity_gate_passed"] = False
```

```python
# _validity_flags — reasons a claim is invalid REGARDLESS of p-value
if tool_name in _CELL_UNIT_TOOLS:          flags.append("cell_unit_not_inferential")
if tool_name in _CIRCULAR_INFERENCE_TOOLS: flags.append("circular_inference_risk")
if _plausibility_suspect(result):          flags.append("technical_artifact_risk")
if has_pvalue and not has_padj:            flags.append("uncorrected_multiple_testing")
```

**Worked examples — why "a small p-value alone never earns a conclusion":**

| Result | p-values | Gate 2 outcome | Why |
|---|---|---|---|
| GSE fibroblasts (2 controls) | down to **1e-119** | `LOW_POWER`, exploratory | only 2 replicates/group |
| Mesangial 814 genes (if unblocked) | tiny | `DESCRIPTIVE_ONLY` | `technical_artifact_risk` overrides |
| Spleen B cell 6v6 null | ~40 significant | `DESCRIPTIVE_ONLY` | artifact fingerprint on a null |
| Real, well-powered, plausible DE | tiny | **`SIGNIFICANT_INFERENTIAL`** ✅ | powered **and** no flags |

In the first three the p-value is "significant" by the usual standard — but the design
is underpowered (power axis) or the inference is invalid (validity axis), so Gate 2
refuses to license a finding.

## 5.6 Deterministic renderer

```python
# agent/output_renderer.py
schema = build_output_schema(name, result, args)   # facts + state, no free text
text  = render_strict_output(schema)                # per-state wording
# footer the frontend reads for the badge:
f"[System] inference_state={state} | interpretation_level={level} | forbidden=[{flags}]"
```

Per-state contracts (`STATE_CONTRACT`) decide what wording is allowed — `DESCRIPTIVE_ONLY`
permits numeric facts but forbids any conclusion or biological narrative.

## 5.7 The ungoverned ablation

`AGENT_GOVERNANCE=off` changes three things deliberately: `_gate` becomes a no-op, the
two inferential tools are swapped for **per-cell** (pseudoreplicating) versions, and the
LLM's own narration is surfaced. This is the arm that produces the false discoveries.

---

# 6. VALIDATION (which tests actually run the agent)

Three tests, but **only one drives the deployed agent end-to-end.**

| Test | What it runs | Runs `run_agent`? | Headline |
|---|---|---|---|
| 1 — null harness | per-cell Wilcoxon vs pseudobulk **t-test** (inlined) | **No** (method) | 1,425 vs **0.47** |
| 2 — agent null sweep | the real `run_agent` (routing → gates → renderer) | **Yes** (agent) | **0% inferential FDR** |
| 3 — power preservation | standalone pseudobulk DESeq2 vs per-cell | **No** (method) | **7,613** genes |

Tests 1 and 3 validate the **statistical unit**; Test 2 validates the **deployed agent**.

## 6.1 Test 1 — method-level null harness

```python
# eval/ablation/null_harness/null_harness.py (core loop)
perm = rng.permutation(n_mice); idx_a, idx_b = perm[:half], perm[half:2*half]
# PER-CELL Wilcoxon (ungoverned): cells as independent units
p_cell = mannwhitneyu(Xd[mask_a], Xd[mask_b], axis=0).pvalue
# PER-MOUSE pseudobulk t-test (governed): one profile per replicate
t, p_pb = ttest_ind(mouse_means[idx_a], mouse_means[idx_b], axis=0)
fp_percell.append((p_cell < 0.05).sum()); fp_pseudobulk.append((p_pb < 0.05).sum())
```

**Result:** per-cell **≈1,425** false genes (100% FDR in all 13 configs); pseudobulk
**≈0.47**. (0.47 is a *t-test* number — the agent uses DESeq2; see Test 2.)

## 6.2 Test 2 — agent-level null (whole firewall, end to end)

```python
# eval/ablation/agent_null_harness/agent_null_sweep.py
res = run_agent([], deseq2_prompt(cell_type), file_id, "mouse")   # full pipeline
def score_agent_result(res):
    deseq2 = next(t for t in res["tool_calls"] if t["name"] == "run_deseq2")
    state = deseq2["result"]["inference_state"]["state"]
    false_discovery = state == "SIGNIFICANT_INFERENTIAL"          # licensed false claim
    return {"n_sig": n_sig, "inference_state": state, "false_discovery": false_discovery}
```

**Result:** 0% *inferential* FDR in both regimes. **2v2** (fenestrated): power gate
catches ~400 raw genes → LOW_POWER. **6v6** (Spleen B cell, well-powered): plausibility
gate catches ~47 → DESCRIPTIVE_ONLY. Without Gate 2, the 6v6 case would be **100%** —
defense-in-depth.

## 6.3 Test 3 — power preservation (method, not agent)

```python
# eval/ablation/power_preservation/power_preservation.py  (standalone, NO run_agent)
def governed_deseq2(counts, meta, ref="non_senescent", alt="senescent"):
    dds = DeseqDataSet(counts=c, metadata=sub, design_factors="group"); dds.deseq2()
    return DeseqStats(dds, contrast=["group", alt, ref]).results_df  # → 7,613 genes
def ungoverned_percell(adata, ...):
    p = mannwhitneyu(a, b, axis=0).pvalue                            # → ~9,652 (per-cell)
```

**Result:** the governed *unit* recovers **7,613** correctly-signed DE genes (CDKN1A
+2.5, IL6 +1.6, MMP3 +2.7, GDF15 +3.5 ↑; MKI67 −5.2, LMNB1 −5.4 ↓). Sensitivity
preserved. If run *through the agent*, this 2-control design would be flagged
`LOW_POWER` — recovered, not licensed.

## 6.4 Wild agent — CellAgent (arXiv:2407.09811)

A published agent, same LLM (Gemini), autonomously **planned and wrote code** for
per-cell `rank_genes_groups` on the null, **ignoring the available `sample_id`
column** = pseudoreplication. **It crashed at QC before executing** (its generic
droplet QC removed all Smart-seq2 cells). The false-gene number (36/101/221) is from
*the harness* running the identical method, **not CellAgent's own run**. Claim only
the *behavior* (the plan), provable from the log.

## 6.5 Unit tests
`test_inference_state.py`, `test_plausibility.py`, `test_deterministic_routing.py`,
`test_intent_router.py`, `test_workflows.py` — **31/31 green** (2026-07-12).

---

# 7. POSITIONING & CONTRIBUTION

The idea sits at the intersection of **four active literatures**. Each component
exists separately; the *combination* — statistical-unit (pseudoreplication) validity
gating, enforced as a **deterministic non-LLM gate**, inside a **single-cell** agent,
validated against **constructed nulls** — is uncovered (literature check, 2026-08-13).

## 7.1 Agent governance / deterministic gates

- **EviBound** (arXiv:2511.05524) — governs *execution* (artifacts exist, run
  finished). A pseudoreplicated claim passes **all** its gates while being false =
  **"faithful but invalid"** (the paper's title). Conceptual contrast.
- **POPPER** (ICML 2025, arXiv:2502.09858) — Type-I control *across a sequence* of
  falsification experiments — not the statistical unit *within* a test.
- **"Reason Less, Verify More"** (arXiv:2607.07405) — the *general* form of our
  architectural thesis: verify each claim by the cheapest sufficient **deterministic**
  mechanism rather than LLM reasoning. Domain-agnostic (policy-violating writes); we
  instantiate the pattern for **statistical-unit semantics**. Cite as the design-pattern
  prior; differentiate on domain + what is being verified.

## 7.2 Statistical-validity-aware agents (the closest threat, 2026)

- **Fisher-R1** (arXiv:2608.07437, Aug 2026) — **nearest neighbor.** Trains an LLM
  agent (RL) for "reliable hypothesis testing," explicitly targeting the failure mode
  where an agent reports a p-value that is *invalid given the data's assumptions* — the
  same *spirit* as Gate 2. **Differentiate on three axes:** (1) training-time RL to make
  the model better vs. our **deterministic gate that never trusts the model**; (2)
  generic tabular hypothesis testing vs. the **statistical-unit / pseudoreplication**
  error specifically; (3) no single-cell / hierarchical-replicate setting. Must be cited.
- **StatABench** (arXiv:2606.22977), **FIRE-Bench** (arXiv:2602.02905) — *benchmarks*
  that measure statistical validity of LLM analysis; they quantify the problem, they do
  not gate it. Cite as motivation (agents demonstrably make these errors), complementary.

## 7.3 Single-cell LLM agents (none govern validity)

- **CellAgent** (arXiv:2407.09811), **scChat** (bioRxiv 2024.10.01.616063),
  **CompBioAgent** (bioRxiv 2025.03.17.643771) — automate scRNA-seq analysis; **none
  has a statistical-validity firewall.** Our CellAgent probe (§6.4) is the empirical
  demonstration of this gap.

## 7.4 The statistics (foundation — not our contribution)

- **Squair et al. 2021** — pseudoreplication + the constructed-null method (foundation).
- Recent methods to cite so the stats framing reads as current (not anchored to 2021):
  **nested-settings DE** (Brief Bioinform 2025, bbaf397), **multi-patient
  pseudoreplication strategies** (bioRxiv 2024.06.15.599144), **dreamlet** / **distinct**
  / mixed-model approaches.

## 7.5 Honest contribution framing

Not a novel method (pseudobulk is textbook; governance exists via EviBound/POPPER;
statistical-validity awareness now exists via Fisher-R1). The contribution is the
**falsifiable empirical demonstration** (deployed agents fail; ground-truth-validated)
+ the specific **statistical-unit gate** as a deterministic firewall, in the single-cell
domain. Findings-tier-to-focused-Proceedings. Target: **ML4H 2026** (~Sept).

---

# 8. THE SUBTLE / HONEST POINTS (what a sharp reviewer probes)

1. **Method vs agent level.** "0.47" and "7,613" are *method/unit* numbers (Tests 1 &
   3, no agent). The **agent-level** evidence is Test 2 (0% inferential FDR) + the demo.
   Don't say "the agent gives 0.47."
2. **The agent's DESeq2 on nulls isn't 0.47.** It's ~47–400 raw genes but **0 false
   conclusions** — the gates, not DESeq2's calibration, do the work.
3. **DESeq2 is anti-conservative at low n** — that's *why* Gate 2 matters, not just the
   unit.
4. **Shrinkage ↔ plausibility coupling.** The 6v6 catch relies on TMS *unshrunk* LFCs
   being large. Naive LFC shrinkage would collapse them → plausibility passes → 6v6
   nulls flip to false discoveries. Shrinkage must be paired with threshold recalibration.
5. **Power-preservation is the 2-control caveat.** The flagship 7,613 comes from a
   design the agent itself would call LOW_POWER. "Preserves power" = *unit sensitivity*,
   not *inferential licensing*.
6. **CellAgent planned, didn't execute.** Never claim it "ran" and "reported."
7. **Mesangial (this session):** 93 cells total → 1–3-cell "replicates" → now BLOCKED
   by Gate 1. Unblocked it gave 814 fake genes (median |LFC|~10, 93% down) from a
   library-size imbalance — a *technical artifact*, not a counts bug.

**Limitations (own them):** low replicate counts in TMS (2–4/group); 2-control GSE;
firewall rigorously demonstrates *pseudoreplication* (min-cells + artifact checks in
place; confounding/circular/multiple-testing are extension points); constructed-failure
ablation + single external agent; single signature (SenMayo).

---

# 9. APPENDIX

## Key numbers
- Null: ungoverned per-cell **1,425** mean false genes (range 63–5,748), **100% FDR in
  all 13 configs**; governed pseudobulk t-test **0.47**. 5 tissues × 13 cell types × 200
  perms.
- Power: **7,613** DE genes (GSE226225, 11 senescent vs 2 control).
- Agent null: 2v2 ~400 raw / LOW_POWER; 6v6 ~47 raw / DESCRIPTIVE_ONLY; **0% inferential
  FDR** both; counterfactual without Gate 2 = 100% at 6v6.
- Mesangial: 93 cells total; 814 fake genes if unblocked; now BLOCKED.
- Shrinkage: proximal tubule 24v18 median |log2FC| 8.2 → 1.6.

## Key constants
- `MIN_CELLS_PER_SAMPLE = 20` (shared: `build_pseudobulk.py` ↔ null harness)
- `MIN_ADMISSIBLE_REPLICATES = 2`, `RECOMMENDED_SAMPLES_PER_GROUP = 3`
- Plausibility: `_IMPLAUSIBLE_MEDIAN_LFC = 5`, `_EXTREME_LFC = 8`,
  `_EXTREME_FRAC_WARN = 0.30`, `_DIRECTION_SKEW_WARN = 0.90`, `_MIN_SIG_FOR_CHECK = 20`
- States: DESCRIPTIVE_ONLY, LOW_POWER, NOT_SIGNIFICANT, SIGNIFICANT_INFERENTIAL, BLOCKED
- Validity flags: cell_unit_not_inferential, circular_inference_risk,
  uncorrected_multiple_testing, technical_artifact_risk

## Key files
| Concern | File |
|---|---|
| Entry / orchestration | `backend/agent/agent.py` (`run_agent`) |
| Pipeline (counts lock, QC/norm/cluster) | `backend/agent/pipeline.py` |
| Tier 1 keyword router | `backend/agent/intent_router.py` |
| Tier 2 intent + validation | `backend/agent/intent_extractor.py` |
| Gate 1 admissibility | `backend/agent/admissibility.py` |
| Tool wiring + `_gate` | `backend/agent/tool_router.py` |
| Pseudobulk (min-cells, raw counts) | `backend/tools/build_pseudobulk.py` |
| DESeq2 + plausibility + volcano | `backend/tools/run_deseq2.py` |
| Per-sample Mann-Whitney | `backend/tools/statistics.py` |
| SenMayo scoring | `backend/tools/senescence.py` |
| Leiden clustering | `backend/tools/clustering.py` |
| Cell-type annotation | `backend/tools/cell_type_annotation.py` |
| Gate 2 inference state | `backend/agent/inference_state.py` |
| Deterministic renderer | `backend/agent/output_renderer.py`, `output_schema.py` |
| Governance toggle | `backend/agent/governance.py` |
| Per-cell ablation tools | `backend/tools/percell_inference.py` |
| Test 1 (method null) | `eval/ablation/null_harness/` |
| Test 2 (agent null) | `eval/ablation/agent_null_harness/` |
| Test 3 (power) | `eval/ablation/power_preservation/` |

## One-paragraph summary
LLM agents doing single-cell DE commit **pseudoreplication** — treating each cell as an
independent sample — producing hundreds to thousands of false discoveries (100% FDR) on
data with no real signal. The Senescence Agent is a **governed single-LLM agent** whose
LLM only proposes; a deterministic **two-gate validity firewall** refuses inadmissible
inferences before they run (Gate 1) and withholds conclusions that a small p-value alone
doesn't justify (Gate 2). Validated against ground truth, it is **silent on constructed
nulls** (0% inferential false-discovery rate, via a power axis and a plausibility axis)
and **sensitive on a real senescence effect** (7,613 correctly-signed genes) — *faithful
but valid*.
