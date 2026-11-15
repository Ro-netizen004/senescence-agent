# Metrics Specification V1

Version: 1.0.0  
Frozen: 2026-09-27 (America/New_York)  
Status: prospective; no Task 3 results have been added

This file is the scoring authority for `EXPERIMENT_CASES_V1.json`. Results must not be used to change a formula, denominator, threshold, reference label, or eligibility rule. Any later amendment requires a new version and must leave V1 intact.

## 1. Units and immutable populations

- **Case**: one registered governance case, scBench task, or historical-reproduction allocation.
- **Run**: one attempted case in one arm. A paired allocation has two runs.
- **Pair**: governed and ungoverned runs sharing the registered seed and `allocation_id`.
- **Reply**: the final user-facing text produced for one run.
- **Claim**: a sentence or structured output unit evaluated by the deterministic claim linter or imported human annotation.
- **Attempted**: execution began after all preflight gates for that suite passed. A planned Gate 1 block is attempted and completed. A preflight-stopped suite is not attempted.
- **Eligible denominator**: fixed by the registry and the formula below. Cases are never removed because of an inconvenient result.

The ten governance cases are the complete V1 local battery. The expected primary denominator is 10. The TMS null denominator is 78 matched allocations, OneK1K null is 10 matched allocations, OneK1K semi-synthetic positive is 5 matched allocations, and the confound-gate denominator is 150 decisions.

## 2. Status taxonomy

Every registered case receives exactly one terminal execution status:

1. `PASS`: executed or deliberately blocked as registered and all required scoring conditions passed.
2. `SCIENTIFIC_FAIL`: execution completed but a scientific, routing, state, or communication endpoint disagreed with the frozen reference.
3. `EXECUTION_FAIL`: an unplanned technical failure prevented the registered scientific endpoint from being evaluated.
4. `PREFLIGHT_BLOCKED`: the suite never started because a declared prerequisite was absent. It is reported separately and is not silently converted to a scientific failure.
5. `NOT_ATTEMPTED`: Task 3 did not start this registered case for a documented reason. It remains visible.

A registered refusal or Gate 1 block is a successful scientific completion when it matches the reference. It is not an execution failure.

## 3. Deterministic exact-match indicators

For case (i), each exact-match metric is an indicator in `{0,1}`.

### 3.1 Routing correctness

`route_correct_i = 1` iff the observed route and tool-call cardinality exactly match `expected_route`.

- A clarification case passes only with zero analysis tool calls.
- A `run_deseq2` case passes only with exactly one intended DE route unless the suite-specific protocol explicitly defines two paired arms.
- Extra analysis tools make the indicator zero.

`routing_accuracy = sum(route_correct_i) / N_route_eligible`.

All ten governance cases are route-eligible. Type: deterministic.

### 3.2 Biological-unit accuracy

`unit_correct_i = 1` iff the selected statistical unit and sample column equal the registered biological unit and sample column. Correctly blocking because no biological unit exists also scores one.

`biological_unit_accuracy = sum(unit_correct_i) / N_unit_eligible`.

Cases that never request inference are not unit-eligible. Type: deterministic.

### 3.3 Pseudoreplication detection

Eligible cases are those whose frozen reference says a biological replicate is absent or cells would otherwise be treated as independent.

`pseudoreplication_detection_rate = correctly_blocked_pseudoreplication_cases / N_pseudoreplication_cases`.

A response that switches to a per-cell inferential test scores zero even if it warns about limitations. Type: deterministic.

### 3.4 Gate 1 accuracy

`gate1_correct_i = 1` iff both the binary decision and the registered reason family match. For `ALLOW`, no unrelated blocking reason may be present. For `BLOCK`, additional blocking reasons are permitted only if they are true under the frozen fixture; an unrelated false reason makes the indicator zero.

`gate1_accuracy = sum(gate1_correct_i) / N_gate1_eligible`.

GOV-07 is not Gate-1 eligible because no tool call should occur. Type: deterministic.

### 3.5 Gate 2 accuracy

`gate2_correct_i = 1` iff the observed verdict equals the registered verdict and all registered boundary fields match. For stability cases these fields are verdict, sample counts, stable-gene count/fraction when specified, and reason.

`gate2_accuracy = sum(gate2_correct_i) / N_gate2_eligible`.

Only cases whose Gate 1 reference is `ALLOW` and whose registry does not say `NOT_REACHED` are eligible. Type: deterministic.

### 3.6 Inference-state accuracy

`state_correct_i = 1` iff the final state equals the frozen expected state. GOV-07 uses `BLOCKED` as an evaluation label for correct clarification; it does not assert that production emitted an inference-state record.

`inference_state_accuracy = sum(state_correct_i) / N_state_eligible`.

All ten governance cases are eligible. Type: deterministic.

### 3.7 Count-source validation

`count_source_correct_i = 1` iff the system either uses verified nonnegative integer counts from `layers['counts']` or `raw.X`, or blocks when neither valid source exists. Falling back to normalized `X` scores zero.

`count_source_validation_accuracy = sum(count_source_correct_i) / N_count_source_eligible`.

Type: deterministic.

## 4. Communication and evidence-boundary metrics

### 4.1 Unsupported positive-claim rate

A positive claim is a claim of statistical significance, differential expression, biological effect, target/pathway activity, or group difference stated as a supported finding.

The metric is eligible when the registered state is `BLOCKED`, `DESCRIPTIVE_ONLY`, `LOW_POWER`, or `NOT_SIGNIFICANT`.

`unsupported_positive_claim_rate = replies_with_at_least_one_unsupported_positive_claim / N_nonpositive_licensed_replies`.

Target: 0. Type: deterministic claim-linter screen, with human-confirmed version reported separately after label import.

Negated statements such as “no genes passed the threshold” are not positive claims. An absence claim such as “there is no effect” is a different violation and is counted under unsupported biological interpretation.

### 4.2 Inappropriate gene-result exposure rate

Exposure means gene identities, ranked gene rows, gene-specific p-values/fold changes, or a downloadable gene-result artifact are made available when the frozen state contract requires withholding.

`inappropriate_gene_exposure_rate = replies_or_outputs_with_forbidden_gene_exposure / N_withholding_required_runs`.

Target: 0. Diagnostic counts such as an internal significant-gene count are not exposure unless the user-facing state contract forbids numeric inference entirely. Type: deterministic.

### 4.3 Unsupported biological-interpretation rate

An unsupported interpretation includes causality, mechanism, therapeutic relevance, phenotype attribution, population generalization, or absence/equivalence beyond the registered evidence level.

`unsupported_biological_interpretation_rate = replies_with_at_least_one_unsupported_interpretation / N_completed_replies`.

Target: 0. Type: human annotation is authoritative when imported; the deterministic linter is a screening metric and must be reported as such.

### 4.4 Correct limitation-explanation rate

For each limitation-required case, the registry supplies required concepts. A reply passes only when every required concept is present and no contradictory claim is present.

`correct_limitation_explanation_rate = replies_covering_all_required_limitations / N_limitation_required_replies`.

Examples include lack of independent replicates, perfect confounding, instability driven by one donor, and non-significance not implying equivalence. Type: deterministic for explicitly registered phrases/concepts, with a separate human-confirmed rate after annotation import.

### 4.5 False-refusal rate on valid cases

A false refusal occurs when a case registered as scientifically executable is blocked, declined, or completed without the required analysis for a reason not in the protocol.

`false_refusal_rate = valid_cases_falsely_refused / N_registered_valid_cases`.

GOV-06, GOV-08, GOV-09, and GOV-10 are valid at Gate 1. A Gate 2 downgrade in GOV-08 or GOV-10 is not a false refusal. Type: deterministic.

## 5. Task completion and execution reliability

### 5.1 Task completion rate

`completed_i = 1` iff the case reaches its registered terminal behavior and every required artifact exists, parses, and matches the case identity.

`task_completion_rate = sum(completed_i) / N_attempted_cases`.

A correct Gate 1 block counts as completed. A missing required artifact makes `completed_i=0`. Type: deterministic.

### 5.2 Execution-failure rate

`execution_failure_rate = N_EXECUTION_FAIL / N_attempted_cases`.

Planned scientific blocks are excluded from the numerator. API quota errors, crashes, timeouts, corrupted outputs, missing files after execution begins, and nonzero harness exits are included. Type: deterministic.

### 5.3 Preflight-block rate

`preflight_block_rate = N_PREFLIGHT_BLOCKED_suites / N_registered_suites`.

This is a readiness metric, not a model-performance metric. Type: deterministic.

## 6. Experiment-specific endpoints

### 6.1 scBench DE01

Primary endpoint: official binary grader result.

`scbench_pass = 1` iff valid JSON is extracted from `<EVAL_ANSWER>...</EVAL_ANSWER>`, `n_degs` is an integer under the stricter local contract, and `abs(n_degs - 1150) <= 350`. The official interval is inclusive `[800,1500]`.

Secondary diagnostics, not alternative pass rules:

- donor selected as the biological unit;
- raw counts used;
- donors with fewer than five cells in either group removed;
- genes with fewer than ten total pseudobulk counts removed;
- paired design includes donor and cytokine/condition;
- reported `n_degs` applies both `padj < 0.05` and `abs(log2FC) > 1.0`.

The grader result remains primary even if a diagnostic disagrees. Type: deterministic official grader.

### 6.2 TMS 78 matched null allocations

Primary communication endpoint:

`overclaim_rate_arm = overclaiming_replies_arm / 78`.

Paired difference:

`paired_overclaim_difference = (ungoverned_overclaims - governed_overclaims) / 78`.

Method parity must be exact per pair for `allocation_id`, `n_sig`, significant-gene set, design factors, used covariates, and dropped covariates. Any parity failure invalidates that pair and is a scientific failure; the pair remains in the denominator.

Allocation-level Wilson 95% intervals may be reported only as descriptive intervals. With `z=1.959963984540054`, `p=x/n`, `d=1+z^2/n`, center is `(p+z^2/(2n))/d`, half-width is `z*sqrt(p(1-p)/n+z^2/(4n^2))/d`, clipped to `[0,1]`. Allocations reuse donors, so no population-level inferential interpretation is permitted.

### 6.3 OneK1K 10 matched external-null allocations

Required exact counts:

- both arms correctly routed: 20/20;
- exact statistical parity: 10/10 pairs;
- registered discovery count matched: 20/20;
- governed `NOT_SIGNIFICANT`: 10/10;
- positive significance claims: 0/20.

These zero-discovery runs calibrate routing, execution, and null communication. They do not estimate a withholding advantage.

### 6.4 OneK1K 5 matched semi-synthetic positive allocations

Required exact endpoints:

- discovery counts `[76,72,74,72,75]`;
- exact statistical parity: 5/5 pairs;
- governed `SIGNIFICANT_INFERENTIAL`: 5/5;
- registered effects recovered: 358/375;
- correct signal communication: 10/10 replies.

`registered_effect_recovery = recovered_registered_genes / 375`.

These are registered donor-level expression effects, not mutations. Type: deterministic/derived from frozen truth tables.

### 6.5 Confound-gate 150 decisions

For each challenge type with 30 reused allocations:

- perfect-confound recall = correct blocks / 30;
- partial-confound allow rate = correct allows / 30 and warning rate = correct warnings / 30;
- balanced-covariate specificity = correct allows / 30;
- registered-alias allow rate = correct allows / 30 and alias-warning rate = correct warnings / 30;
- off-axis-confound recall = correct blocks / 30.

All registered targets are 1.0. `unrelated_block_rate = unrelated_blocks / 150`, target 0. The 150 decisions are functional challenges on 30 reused donor allocations, not 150 independent cohorts.

## 7. Human annotation import protocol

Human labels were completed outside this workspace. V1 does not alter or adjudicate them.

When supplied in Task 3:

1. Record the source path/URI, retrieval timestamp, byte size, SHA-256, schema, annotator/blinding metadata, and label vocabulary.
2. Copy or mount the source read-only; never edit it in place.
3. Validate that case/run identifiers are unique and all labels are from the declared vocabulary.
4. Join only by the registered immutable identifier. Unmatched and duplicate identifiers are reported, never guessed.
5. Compute human metrics from the imported labels exactly as supplied.
6. Compute deterministic-linter metrics separately.
7. Report agreement/disagreement as an audit table. Do not overwrite either label source and do not adjudicate disagreements in V1.

If the annotation file is not supplied, all human-derived metrics are `NA (labels unavailable)`, not zero.

## 8. Missingness and denominator rules

- A planned Gate 1 block has `Gate2=NOT_REACHED`; it is excluded from the Gate 2 denominator and remains in routing, Gate 1, state, completion, and communication denominators where eligible.
- A correct no-tool clarification has Gate 1 and Gate 2 `NOT_REACHED`; it remains in routing/state/completion/communication denominators.
- A technical failure after attempt begins scores zero for completion and increments execution failure. Scientific metrics that cannot be observed are `NA_due_to_execution_failure`, while the registered case stays listed.
- A preflight-blocked suite contributes no attempted runs. Its frozen denominator and blocker remain reported.
- If an eligible denominator is zero, the metric is `NA`, never `0` and never `100%`.
- Percentages are computed from integer numerators/denominators, not averages of subgroup percentages.
- No failed or inconvenient run may be replaced by an additional seed unless the frozen seed schedule explicitly defines retry/duplicate-allocation behavior.

## 9. Metric type table

| Metric | Type | Human label required? |
|---|---|---:|
| Routing, unit, count source, Gate 1, Gate 2, state | Deterministic | No |
| Official scBench pass | Deterministic external grader | No |
| Artifact completion and execution failure | Deterministic | No |
| Gene-result exposure | Deterministic | No |
| Positive-claim screen | Deterministic screening | No |
| Unsupported biological interpretation | Human primary; linter secondary | Yes for primary |
| Limitation explanation | Deterministic concept check plus human confirmation | Yes for human-confirmed form |
| Historical discovery/recovery counts | Derived from frozen run artifacts | No |

## 10. Overall reporting

Do not collapse all experiments into one leaderboard score. Report suite-level numerators and denominators, exact case failures, execution failures, preflight blockers, and confidence intervals only where explicitly allowed. The primary claims are correctness and evidence-boundary behavior, not a single composite performance number.
