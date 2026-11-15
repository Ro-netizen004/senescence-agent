# Experiment Protocol V1.2 — Task 3B Technical Replication

Version: 1.2.0  
Preregistration date: 2026-09-29 (America/New_York)  
Parent scientific protocol: `EXPERIMENT_PROTOCOL_V1.md`  
Parent retrieval amendment: `EXPERIMENT_PROTOCOL_V1_1.md`  
Scope: one prospective technical replication of scBench `DE01_pseudobulk_de`  
Status at registration: preregistered before V1.2 scientific execution

## 1. Relationship to V1.1

Task 3B V1.1 is permanently preserved at:

`eval/results/task3b/scbench_de01_v1_1_20260929_01`

It remains an `EXECUTION_FAIL` with one Gemini attempt, one DESeq2 call, one
official-grader call, zero retries, and preserved `n_degs = 1328`. Its original
33-entry manifest SHA-256 is
`8f9a586a56559021eeb7f89abc88568d8c48ddc1f1ab1f7cb116c468623bb70b`.
Its separately labeled post-failure recoveries remain forensic evidence and are
not reclassified as original V1.1 outputs.

V1.2 is a new, prospective technical replication after that preserved
infrastructure failure. It does not overwrite, repair in place, rescore, or
continue V1.1.

## 2. Authorized technical corrections

V1.2 corrects only two known infrastructure defects:

1. **Gemini authentication.** A newly configured private credential must pass a
   non-scientific access preflight for registered model `gemini-3.5-flash`.
   During the registered V1.2 execution the Gemini analysis plan must be returned
   and accepted by the unchanged validator. Deterministic fallback is prohibited.
   Any provider error, empty proposal, validation correction, or fallback status
   makes the single V1.2 attempt an execution failure and stops before DESeq2.
2. **Official-grader result serialization.** The unchanged
   `latch-eval-tools==0.3.10` grader returns a standard dataclass
   `GraderResult`. V1.2 serializes it with `dataclasses.asdict`, which was verified
   on synthetic objects. It must not call the known-failing `.dict()` path and
   must not alter any grader input, field, calculation, or decision.

No other V1.2 difference is authorized.

## 3. Frozen scientific inputs and settings

The following remain identical to V1/V1.1:

- task: `DE01_pseudobulk_de`;
- scBench commit: `0bc34032bfa402dad29fc40b4cf10ea8fc03193e`;
- task JSON SHA-256:
  `b28e0e60648e6543c695d7cfb100f6facde9b0421e184187fc324221afec167b`;
- dataset node: `latch://158542059.node`;
- resolved dataset: `Parse_10M_PBMC_100K_subset.h5ad`;
- dataset byte size: `1,590,563,176`;
- dataset SHA-256:
  `bf784ee3fdfd0bf2b93b9d05f194a53215437fdc5ec4e60d84388e0bd52c7f9d`;
- exact prompt and exact answer schema;
- model: `gemini-3.5-flash`;
- planner temperature: `0` and all other registered model settings;
- population: exact label `CD14 Mono`;
- contrast: `IFN-beta` versus reference `PBS`;
- biological unit: donor;
- exclude donors with fewer than 5 cells in either condition;
- verified raw nonnegative integer counts only;
- sum raw counts per donor × condition;
- retain genes with at least 10 total pseudobulk counts;
- paired design factors: `donor + cytokine`;
- unchanged pyDESeq2 implementation/settings and contrast direction;
- DEG threshold: `padj < 0.05` and `|log2FC| > 1.0`;
- unchanged production Gate 1, Gate 2, inference-state, and output-firewall logic;
- official grader package: `latch-eval-tools==0.3.10`;
- official numeric-grader source SHA-256:
  `ce0e235234d32180f995281e7797639fbe817547cc63095be36380cb4f844a02`;
- official answer-extraction source SHA-256:
  `b80a5cb310043d95f9a3c0e042884ce402bb3f4b3abe77e02ca9dd5470e6886d`;
- expected `n_degs = 1150`, absolute tolerance `±350`, and inclusive pass
  interval `[800,1500]`;
- all V1 metric definitions, denominators, failure taxonomy, interpretation
  constraints, and paper-claim rules.

V1.2 introduces no production scientific-code change. Its evaluation runner
must import the V1.1 scientific preprocessing, adapter, Gate-1, threshold, and
formatting helpers without editing them, and invoke the same unchanged
production DESeq2/Gate-2/state/renderer entry points.

## 4. Required preflight before the attempt marker

All of the following must pass before scientific execution:

1. V1.1 remains `EXECUTION_FAIL`, its original manifest verifies, and its
   directory is not modified.
2. This protocol has a recorded SHA-256 and a frozen copy in the new result
   directory.
3. The registered task JSON, V1/V1.1 files, metrics, package freeze, scBench
   commit, and dataset identity match their frozen hashes.
4. The staged dataset remains mode `0444`/read-only.
5. Python 3.11.9, `.venv-task2`, `pip check`, exact `TASK2_PIP_FREEZE.txt`,
   writable `MPLCONFIGDIR`, and inactive report-model/report-key overrides pass.
6. A non-scientific `models.get` call with a persistent Gemini client verifies
   authenticated access to `gemini-3.5-flash`. No DE01 content may be sent.
7. A dummy `GraderResult` verifies `dataclasses.asdict` field preservation and
   JSON round-trip, while confirming `.dict()` is absent. The DE01 grader must
   not run during this preflight.
8. V1.2 runner tests, V1.1 runner tests, and the existing targeted governance
   suite pass.
9. Source/hash checks establish that no scientific production file changed.

Any failure is `PREFLIGHT_BLOCKED`; no registered V1.2 attempt may begin.

## 5. Single registered execution

The new result directory is:

`eval/results/task3b/scbench_de01_v1_2_20260929_01`

An irreversible attempt marker must be written before the registered Gemini
planner call. The execution count and retry count are fixed at one and zero.
The trace must preserve:

1. exact prompt and dataset identity;
2. authoritative dataset profile and literal label resolution;
3. deterministic route plus the actual Gemini proposal and validator audit;
4. exact population, conditions, biological unit, and donor eligibility;
5. lossless evaluation adapter and production Gate-1 checks;
6. exact raw-count donor × condition pseudobulk matrix;
7. ≥10-total-count gene filtering and paired donor-plus-cytokine design;
8. one DESeq2 invocation and its complete result table;
9. exact preregistered significance thresholding;
10. production Gate-2 results;
11. inference state and deterministic governed rendering/output firewall;
12. exact `<EVAL_ANSWER>`;
13. one official answer-extraction/grader invocation;
14. successful dataclass-safe serialization of every `GraderResult` field;
15. stdout, stderr, failures, call counts, environment, and complete manifests.

If Gemini fails or is not accepted, preserve `EXECUTION_FAIL` and stop before
DESeq2. If any later component fails, preserve the failure without retry. An
unfavorable scientific result must be reported unchanged and must not trigger a
rerun.

## 6. Call accounting

The non-scientific preflight model-access request is recorded separately from
the registered execution. The registered V1.2 execution permits exactly:

- one Gemini planner call;
- one DESeq2 call, only after an accepted Gemini plan and Gate-1 allow;
- one official grader call, only after the exact answer is serialized;
- zero scientific retries.

No report-model call is authorized.

## 7. Interpretation and stopping rule

V1.2 can establish only the performance of this one prospectively registered
technical replication. It cannot erase V1.1, prove provider-weight
reproducibility, generalize to other scBench tasks or datasets, establish causal
biology, or authorize Task 3C automatically.

Task 3C must not begin in the same operation, regardless of V1.2 outcome.
