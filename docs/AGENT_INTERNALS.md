# Agent Internals — End-to-End Walkthrough

Reference for how the Senescence Agent works and how it is validated, with real
code. Written for paper methods, Q&A prep, and onboarding.

**Core principle:** the LLM only ever *proposes* (routing/intent). Every statistic,
every claim-permission, and all user-facing prose are **deterministic**. The three
validation tests (§8–§10) show the system is *silent on nulls, sensitive on real
signal, and honest at the conclusion*.

**One-line flow:**
`/chat → cache + pipeline → Tier 1/2/3 routing → Gate 1 (admissibility, pre-exec) →
deterministic tool (pseudobulk / per-sample) → Gate 2 (inference state + validity
flags, post-exec) → deterministic renderer`

---

## 1. Entry point → data preparation

`POST /chat` (`main.py`) calls `run_agent`. The dataset is loaded once, cached
in-process, and run through a deterministic Scanpy pipeline.

```python
# agent/agent.py — run_agent
adata = get_adata(file_id)                 # in-memory cache (TTL 1h, max 3)
if adata is None:
    adata = sc.read_h5ad(resolve_dataset_path(file_id))
    cache_adata(file_id, adata)
ensure_pipeline(adata, species)            # QC / normalize / cluster, idempotent
governed = governance_enabled()            # production = True always
```

`ensure_pipeline` is idempotent (guarded by `pipeline_state`) and **locks raw
integer counts** into `layers['counts']` — DESeq2 must see counts, never normalized
values:

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

The `dataset_profile` (sample/replicate column, age/group column, cell-type column)
is the **single source of truth** every downstream component reads — and what the
column-roles UI overrides.

---

## 2. Three-tier routing — "trust the LLM as little as possible"

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

**Tier 1** — pure string matching, no model:

```python
# agent/intent_router.py — route()
if _wants_analysis_panel(message):                  # "run a full analysis", …
    return RouteDecision(workflow_id="panel")
if _wants_deseq2(message):
    parsed = _parse_deseq2_template(message, adata, profile)  # regex over real cols
    if parsed:
        return RouteDecision(workflow_id="deseq2", tool_args={"run_deseq2": {...}})
```

**Tier 2** — the LLM emits a *schema-constrained* intent; a deterministic validator
confirms it against the real data and **rejects anything invented**:

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

The LLM is even handed the real cell-type/age lists up front (`_dataset_context`),
so it is fenced in going in and validated coming out. Design comment: *"LLM
proposes, deterministic validator disposes."*

**Tier 3** — classic tool-calling loop; the model chooses tools/args itself. Even
here the tools are the *governed* tools and the reply is deterministic:

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

---

## 3. Gate 1 — Admissibility (before the tool runs)

Every inferential tool is wrapped by `_gate`. The check runs *before* execution; if
the design can't support the inference, the tool never runs:

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

`check_admissibility` (`agent/admissibility.py`) inspects the *design*:

```python
# a sample counts as a replicate ONLY if it has ≥ MIN_CELLS_PER_SAMPLE (=20) cells
reps, excluded = _replicates_per_group(scoped, sample_col, group_col, groups,
                                       MIN_CELLS_PER_SAMPLE)
low = [g for g, n in reps.items() if n < MIN_ADMISSIBLE_REPLICATES]   # < 2
if low:
    reasons.append("insufficient_replicates: … a per-cell test would be pseudoreplication.")
confounders = _confounded_with(scoped, sample_col, group_col, groups)  # perfect separation
```

Refuses four design failures: **no replicate column, < 2 usable replicates/group,
confounded contrast, circular (cluster-defined) DE**. `MIN_CELLS_PER_SAMPLE` is
shared with the null harness so production and evaluation never drift.

---

## 4. The tools — the deterministic statistical core

DESeq2 aggregates to the **biological replicate** (pseudobulk) — the pseudoreplication
fix — then runs the model, then a result-plausibility check:

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

`test_senescence_difference` does the same at the score level: it tests **per-sample
medians** (Mann-Whitney), never per-cell values.

---

## 5. Gate 2 — Justification (after the tool runs)

Every governed result is post-processed before it can be rendered:

```python
# agent/agent.py — _execute_tool
result = tool_map[name](args)
if governed and isinstance(result, dict):
    result = apply_inference_state(name, result, args)   # attaches inference_state block
```

Five states, then **validity flags override significance**:

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

**Two independent axes** downgrade a "significant" result to descriptive-only: too
few replicates (power) or an artifact fingerprint (plausibility).

---

## 6. Deterministic renderer — the interpretation firewall

```python
# agent/output_renderer.py
schema = build_output_schema(name, result, args)   # facts + state, no free text
text  = render_strict_output(schema)                # per-state wording
# footer the frontend reads for the badge:
f"[System] inference_state={state} | interpretation_level={level} | forbidden=[{flags}]"
```

Per-state contracts (`STATE_CONTRACT`) decide what wording is allowed — e.g.
`DESCRIPTIVE_ONLY` permits numeric facts but forbids any conclusion or biological
narrative.

---

## 7. The ungoverned ablation (comparison arm)

`AGENT_GOVERNANCE=off` changes three things deliberately: `_gate` becomes a no-op,
the two inferential tools are swapped for **per-cell** (pseudoreplicating) versions,
and the LLM's own narration is surfaced. This is the arm that produces the false
discoveries the firewall prevents.

```python
# tool_router.py (ungoverned) — cells treated as independent samples
from tools.percell_inference import differential_expression_percell
# agent.py — no apply_inference_state; LLM text returned verbatim
```

---

## Validation — which tests actually run the agent?

Three tests, but **only one drives the deployed agent end-to-end.** Read this table
before citing any number:

| Test | What it runs | Runs `run_agent`? |
|---|---|---|
| 1 — null harness (§8) | per-cell Wilcoxon vs pseudobulk *t-test* (inlined) | **No** — method-level |
| 2 — agent null sweep (§9) | the real `run_agent` (routing → gates → renderer) | **Yes** — agent-level |
| 3 — power preservation (§10) | standalone pseudobulk DESeq2 vs per-cell (inlined) | **No** — method-level |

Tests 1 and 3 validate the **statistical unit** the agent's governance relies on
(silent on nulls, sensitive on real signal). Test 2 validates the **deployed agent**
itself. The interactive app (mesangial block, GSE recovery) is additional agent-level
evidence.

---

## 8. Validation Test 1 — method-level null harness

**Constructed null (Squair 2021):** randomly relabel *whole mice* into two fake
groups within one cell type → truth = **0** DE genes; every reported gene is a false
positive.

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
**≈0.47**. FDR correction alone does *not* fix per-cell — the fix is the *unit*.

> Note: "0.47" is a **method-level** number (pseudobulk *t-test*). The deployed agent
> uses DESeq2, which yields more raw genes on nulls (~47 at 6v6, ~400 at 2v2) but
> **0 licensed conclusions** — see Test 2.

---

## 9. Validation Test 2 — agent-level null (whole firewall, end to end)

Drives the **real `run_agent`** on constructed nulls and scores its *inference state*
(not isolated statistics):

```python
# eval/ablation/agent_null_harness/agent_null_sweep.py
res = run_agent([], deseq2_prompt(cell_type), file_id, "mouse")   # full pipeline
def score_agent_result(res):
    deseq2 = next(t for t in res["tool_calls"] if t["name"] == "run_deseq2")
    state = deseq2["result"]["inference_state"]["state"]
    false_discovery = state == "SIGNIFICANT_INFERENTIAL"          # licensed false claim
    return {"n_sig": n_sig, "inference_state": state, "false_discovery": false_discovery}
```

**Result:** 0% *inferential* false-discovery rate in both regimes. At 2v2 the **power
gate** catches ~400 raw genes (`LOW_POWER`); at 6v6 the **plausibility gate** catches
~47 (`DESCRIPTIVE_ONLY`). Without Gate 2 the 6v6 case would be 100% — defense-in-depth.

> Coupling caveat: the 6v6 catch relies on TMS *unshrunk* DESeq2 producing large LFCs.
> Adding LFC shrinkage would collapse them and require re-calibrating the plausibility
> thresholds, or the 6v6 nulls would flip to `SIGNIFICANT_INFERENTIAL`.

---

## 10. Validation Test 3 — power preservation (stays sensitive)

**This is the statistical *method*, not the agent.** `power_preservation.py` is a
standalone script — `governed_deseq2` / `ungoverned_percell` inlined; it never calls
`run_agent`, the gates, or the inference-state machine. It measures the governed
*unit* on a *real* effect (GSE226225 senescent vs control):

```python
# eval/ablation/power_preservation/power_preservation.py
def governed_deseq2(counts, meta, ref="non_senescent", alt="senescent"):
    dds = DeseqDataSet(counts=c, metadata=sub, design_factors="group"); dds.deseq2()
    return DeseqStats(dds, contrast=["group", alt, ref]).results_df  # → 7,613 genes
def ungoverned_percell(adata, ...):
    p = mannwhitneyu(a, b, axis=0).pvalue                            # → ~9,652 (per-cell)
```

**Result:** the governed *unit* recovers **7,613** correctly-signed DE genes (silent
on nulls at 0.47, detective on real effects) — so pseudobulk preserves sensitivity.
This is a **method-level** claim about the statistical unit, *not* the agent
concluding. Separately: if you ran this same 2-control design *through the agent*, its
power gate would stamp it `LOW_POWER` / descriptive-only — so the 7,613 are
*recovered*, never an inferential conclusion licensed at n=2 control.

---

## 11. Unit tests (`backend/tests/`)

- `test_inference_state.py` — five states + the artifact/low-power overrides
- `test_plausibility.py` — artifact thresholds
- `test_deterministic_routing.py` / `test_intent_router.py` — Tier 1/2 routing
- `test_workflows.py` — workflow assembly

All **31/31 green** as of 2026-07-12.

---

## Key files index

| Concern | File |
|---|---|
| Entry / orchestration | `backend/agent/agent.py` (`run_agent`) |
| Pipeline (QC/norm/cluster, counts lock) | `backend/agent/pipeline.py` |
| Tier 1 keyword router | `backend/agent/intent_router.py` |
| Tier 2 intent + validation | `backend/agent/intent_extractor.py` |
| Gate 1 admissibility | `backend/agent/admissibility.py` |
| Tool wiring + `_gate` | `backend/agent/tool_router.py` |
| Pseudobulk (min-cells, raw counts) | `backend/tools/build_pseudobulk.py` |
| DESeq2 + plausibility | `backend/tools/run_deseq2.py` |
| Gate 2 inference state | `backend/agent/inference_state.py` |
| Deterministic renderer | `backend/agent/output_renderer.py`, `output_schema.py` |
| Governance toggle | `backend/agent/governance.py` |
| Test 1 (method null) | `eval/ablation/null_harness/` |
| Test 2 (agent null) | `eval/ablation/agent_null_harness/` |
| Test 3 (power) | `eval/ablation/power_preservation/` |
