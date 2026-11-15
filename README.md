# Senescence Agent

Senescence Agent is a Python system for single-cell RNA-seq analysis with controlled statistical reporting. A language model can interpret a request and choose an analysis tool. Python checks whether the proposed comparison is admissible, runs the statistical method, assigns an inference state, and renders the user-facing result from a constrained schema.

We built it to study a practical failure mode: a plausible scientific answer can overstate a result when cells are treated as independent replicates, the design is confounded, numerical fitting is unreliable, or a report drops qualifications that were present in the analysis. The project is an audit of those boundaries, not a new senescence classifier.

## Implementation

The API in `backend/main.py` accepts AnnData uploads and chat requests. `backend/agent/` handles intent, planning, tool routing, Gate 1 admissibility, Gate 2 inference state, and final output schema and rendering. `backend/tools/` contains Scanpy processing, sample-level comparisons, raw-count pseudobulk construction, PyDESeq2 differential expression, and senescence scoring with the included SenMayo gene list. The React client in `frontend/` is an optional interface.

Gate 1 checks the requested biological unit, available replicates, group and covariate structure, count validity, and design before inferential tools run. Gate 2 evaluates the returned statistical result and its reliability signals before licensing significance language or gene-level output. The renderer uses that license to construct the final report. These are separate checks: passing Gate 1 does not imply that a fitted result supports an inferential claim.

## Experiments represented in the code

| Family | What was tested | Code |
| --- | --- | --- |
| Task 3A and 3D | Governance-runner source and a human-annotation analysis pipeline | `eval/task2/`, `eval/scripts/task3d/` |
| E1 | Nine CRISPRi targets, original statistical pipeline and reporting interface | `eval/scripts/e1/` |
| E1-S | Saved-result donor stability and numerical sensitivity checks; the R DESeq2 reference script is a separate, prospective specification | `eval/scripts/e1s/` |
| E2 | Four reporting arms over 102 evidence contexts, including the metadata adapter, frozen scorer, Gemini 3.6 execution path, and controlled continuation | `eval/scripts/e2/`, `eval/scripts/e2_model36_v1/`, `eval/scripts/e2_continuation_v1/` |
| E3 | Offline, synthetic architecture ablation of Gate 1 and Gate 2 | `eval/scripts/e3/` |
| R1–R3 | Post hoc field-transfer, numerical-parser, and fixed-wording sensitivity analyses of saved artifacts | `eval/scripts/retrospective/` |

The E2 execution produced 398 complete reports out of 408 planned slots; eight were truncated and two API calls timed out. The original strict numerical-retention score for engineered-positive cases was 0/50 opportunities in each generated-text arm. A later, explicitly post hoc parser found correctly matched numeric values in saved LaTeX-formatted rows that the strict parser missed. That finding concerns measurement of report content, not biological correctness. The E3 fixture tests the behavior of the existing gates on synthetic designs; it is not external biological validation. Independent E4 scientific-claim annotation has not been completed, so the machine screens and claim linter should not be treated as scientific ground truth.

## Install

The supported backend runtime is Python 3.11.x; the local evaluation environment used Python 3.11.9. `backend/requirements.txt` pins the Python analysis and API dependencies. The locally verified environment had Scanpy 1.11.5, PyDESeq2 0.5.4, and `google-genai` 2.18.1, and passed `pip check`. R 4.6.1 was present locally, but the required R package DESeq2 1.52.0 was not installed; the R reference script has not been verified in this environment. Task 3B's official scBench path additionally requires the separately frozen `latch==2.77.1` and `latch-eval-tools==0.3.10` toolchain, which is not installed in the current Python environment.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python -m pip check
```

Copy `.env.example` to `.env` and set a private `GEMINI_API_KEY` only if running model-backed requests. Never commit `.env`. The ordinary agent's default model is `gemini-flash-latest`; registered experiments pin their own model and generation settings and must not be silently redirected.

To start the API from the repository root:

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

The `/health` endpoint is a local check. Upload an `.h5ad` through `/upload`, then use `/chat` for analysis and `/report` for a report from accumulated tool runs. Statistical analyses are invoked through those API/tool paths; `backend/tools/run_deseq2.py` is a library module, not a standalone command. The frontend can be started separately with `npm ci` and `npm run dev` from `frontend/`.

## Deterministic checks and reproduction

These commands do not call a model or rerun a biological experiment:

```bash
python -m unittest discover -s backend/tests -p 'test_output_firewall.py'
python -m unittest discover -s eval/scripts/e1s -p 'test_e1s.py'
PYTHONPATH=backend:eval/scripts/e2:eval/scripts/e2_model36_v1:eval/scripts/e2_privacy_v1:eval/scripts/e2_launch_v1 python -m unittest discover -s eval/scripts/e2_launch_v1 -p 'test_orchestrator.py'
python -m unittest discover -s eval/scripts/retrospective -p 'test_retrospective.py'
```

`eval/scripts/e3/run_ablation.py` reads its checked-in synthetic `cases.json`, calls the production Gate 1 and Gate 2 functions, and writes to a new ignored `eval/results/v2/e3/code_reproduction/` directory. It refuses to reuse that directory. Run it only when you intend to generate a new deterministic evaluation record:

```bash
python eval/scripts/e3/run_ablation.py
```

The original E1 and E2 scripts require their frozen evidence packets, result manifests, and external source datasets; these large or potentially sensitive artifacts are not in this code repository. E1 analysis is staged with `python eval/scripts/e1/execute_e1.py analyze` after its registered preparation, and its report stage uses `python eval/scripts/e1/execute_e1.py report`. E2's generated arms require the registered paid Gemini model and an authorized, privacy-minimized evidence export; do not run `eval/scripts/e2/execute.py` as a smoke test. The R1–R3 source copies require the separately archived E1/E2 records and baseline analysis files. Set `SENESCENCE_RETRO_OUTPUT` to a fresh copy of the archived analysis directory for replay; the code defaults to a new ignored reproduction path, not the sealed archive. `eval/scripts/e1s/independent_deseq2.R` additionally requires DESeq2 1.52.0 and prepared paired count matrices.

The Task 3 case registry and the safe V1.2 and metrics specifications are included for source review. The original V1/V1.1 protocols and Task 3B/3C runners contain hard-coded personal paths and are withheld from this public code branch, along with files that depend on those runners. Full Task 3A–3C reproduction therefore requires the separately preserved private originals, external datasets, API access and frozen result archives. Do not rerun a registered scientific case to replace a failure.

## Limits

A deterministic gate can enforce its programmed statistical and reporting rules, but that does not by itself prove that a biological interpretation is correct. The E1 reporting interface lost some upstream design and warning information; the later E2 adapter is a distinct evaluation interface. E2 compares generated reports with local deterministic templates under different output mechanisms, and its incomplete slots remain failures. E3 uses constructed fixtures. The retrospective R1–R3 analyses were performed after observing original outcomes. The repository does not contain completed independent E4 annotations, restricted or raw donor data, or the large original result dumps.

The project is distributed under [LICENSE](LICENSE).
