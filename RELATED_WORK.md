# Related Work — Senescence Agent / Governed Inference

Curated bibliography for the paper. Organized by relationship to our contribution:
**demonstrating that single-cell agents commit pseudoreplication, and that a
statistical-unit governance gate prevents it, validated via constructed-null
ground truth.**

Positioning note on each entry = how to cite/distinguish it in the paper.

Last updated: 2026-06-30. Verify arXiv IDs and venues before camera-ready
(several are 2025–2026 preprints).

---

## 1. Agent governance frameworks (the adjacent layer — concede general idea)

These establish "architectural governance prevents false claims." We concede the
general idea to them and claim only the **statistical-unit layer** they don't touch.

- **EviBound: Evidence-Bound Autonomous Research — A Governance Framework for
  Eliminating False Claims** (2025). arXiv:2511.05524.
  https://arxiv.org/abs/2511.05524
  *Positioning:* Governs **execution** — dual gates verify artifacts exist, runs
  finished, metrics match acceptance criteria. Explicitly disclaims statistical
  validity ("execution-only focus", §5.3.3). A pseudoreplicated DE analysis passes
  every EviBound gate. We govern the layer **beneath**: validity of the statistical
  unit, before any test is meaningful.

- **POPPER: Automated Hypothesis Validation with Agentic Sequential
  Falsifications** (ICML 2025). arXiv:2502.09858. https://arxiv.org/abs/2502.09858
  Code: https://github.com/snap-stanford/POPPER
  *Positioning:* Controls Type-I error **across a sequence of falsification
  experiments**. Assumes each individual test is valid. Pseudoreplication occurs
  one level below — inside a single test, in the choice of statistical unit — where
  POPPER's sequential control does not reach.

---

## 2. Single-cell analysis agents (the target — show they fail)

The deployed agents whose statistical-unit handling we audit. None show a
statistical-unit / pseudoreplication guardrail in their published descriptions.

- **CellAgent: An LLM-driven Multi-Agent Framework for Automated Single-cell Data
  Analysis** (2024). arXiv:2407.09811. https://arxiv.org/abs/2407.09811
  *Positioning:* Planner/executor/evaluator; self-evaluates analysis *quality*,
  not statistical validity. Primary candidate for the "deployed agent commits
  pseudoreplication" demonstration.

- **scPilot: Large Language Model Reasoning Toward Automated Single-Cell Analysis
  and Discovery** (2026). arXiv:2602.11609. https://arxiv.org/html/2602.11609v1
  *Positioning:* LLM + bioinformatics tool library; evaluated on scBench. No
  statistical-unit guardrail described. Secondary demonstration target.

- **ELISA: An Interpretable Hybrid Generative AI Agent for Expression-Grounded
  Discovery in Single-Cell Genomics** (2026). arXiv:2603.11872.
  https://arxiv.org/abs/2603.11872
  *Positioning:* scGPT embeddings + BioBERT retrieval + LLM interpretation.
  Interpretation-focused; no claim-gating on statistical unit.

- **CompBioAgent: An LLM-powered agent for single-cell RNA-seq data exploration**
  (2025). bioRxiv 2025.03.17.643771.
  https://www.biorxiv.org/content/10.1101/2025.03.17.643771v1
  *Positioning:* NL → structured query for data exploration. Exploration, not
  inferential testing — illustrates the breadth of agents lacking the gate.

- **Biomni** (Stanford, 2025) — general biomedical agent, 100+ tools.
  *Positioning:* General-purpose; cite as evidence the field optimizes autonomy/
  capability, not statistical governance. (Add exact ref before submission.)

---

## 3. Pseudoreplication in single-cell (the statistics — concede the fix)

The fix (pseudobulk / mixed models) is textbook. We do NOT claim methodological
novelty here; we cite these as the established correctness standard our gate enforces,
and as the source of the constructed-null demonstration technique.

- **Squair et al., Confronting false discoveries in single-cell differential
  expression** (Nature Communications, 2021).
  https://www.nature.com/articles/s41467-021-25960-2
  *Positioning:* THE pseudoreplication paper. Establishes the failure mode and the
  null/permutation demonstration method we adopt. Cite prominently as motivation.

- **Zimmerman et al., A practical solution to pseudoreplication bias in single-cell
  studies** (Nature Communications, 2021).
  https://www.nature.com/articles/s41467-021-21038-1
  *Positioning:* Pseudobulk aggregation + mixed models as the fix. The "known best
  practice" our gate operationalizes.

- **Single-cell differential expression analysis between conditions within nested
  settings** (Briefings in Bioinformatics, 2025).
  https://academic.oup.com/bib/article/26/4/bbaf397/8232550
  *Positioning:* Most recent (2025) statement that statistical-unit handling
  "needs to be urgently addressed." Shows the problem is live, not settled — and
  that no one has framed it as agent governance.

- **Pseudobulk with proper offsets has the same statistical properties as GLMMs in
  single-cell case-control studies** (Bioinformatics, 2024).
  https://academic.oup.com/bioinformatics/article/40/8/btae498/7730101
  *Positioning:* Justifies pseudobulk as the principled aggregation our gate uses.

---

## 4. Agent reliability / statistical-error benchmarks (the crowding perimeter)

General benchmarks now measure agent statistical errors. None target single-cell
pseudoreplication specifically. Cite to show the area is active and to contrast scope.

- **BioDSA-1K: Benchmarking Data Science Agents for Biomedical Research** (2025).
  arXiv:2505.16100. https://arxiv.org/pdf/2505.16100
  *Positioning:* Measures Type-I/Type-II error of biomedical agents on hypothesis
  validation — closest "agents make statistical errors" work. But general tabular/
  biomarker tasks, not single-cell pseudoreplication, and measures error rather than
  gating the statistical unit.

- **scBench: Evaluating AI Agents on Single-Cell RNA-seq Analysis** (2026).
  arXiv:2602.09063. https://arxiv.org/abs/2602.09063
  Code: https://github.com/latchbio/scbench
  *Positioning:* 394 verifiable scRNA-seq tasks, deterministic graders; frontier
  models 29–53%. Standard benchmark to position against; its DE tasks are where our
  statistical-unit concern bites.

- **FIRE-Bench: Evaluating Agents on the Rediscovery of Scientific Insights** (2026).
  arXiv:2602.02905. https://arxiv.org/pdf/2602.02905
  *Positioning:* Scientific-insight rediscovery benchmark; general, not statistical-
  unit focused.

---

## 5. LLM overclaiming / statistical validity (the problem statement)

Establishes that LLM outputs violate independence and inflate significance — the
general problem our work instantiates concretely for single-cell.

- **From Prompts to Constructs: A Dual-Validity Framework for LLM Research in
  Psychology** (2025). arXiv:2506.16697. https://arxiv.org/pdf/2506.16697
  *Positioning:* Independence violations inflate effect sizes/significance — our
  pseudoreplication argument, generalized. Problem statement, not a system.

- **Do LLM Agents Know How to Ground, Recover, and Assess? A Benchmark for Epistemic
  Competence in Information-Seeking Agents** (2025). arXiv:2509.22391.
  https://arxiv.org/pdf/2509.22391
  *Positioning:* Calibration/abstention based on evidence sufficiency, but for
  information-seeking, not statistical analysis of data.

- **A Survey on Large Language Model-based Agents for Statistics and Data Science**
  (The American Statistician, 2025).
  https://www.tandfonline.com/doi/full/10.1080/00031305.2025.2561140
  *Positioning:* Survey establishing the subfield; situates our contribution.

---

## 6. Foundational domain references (methods we use)

- **Saul et al., A new gene set identifies senescent cells and predicts
  senescence-associated pathways across tissues (SenMayo)** (Nature Communications,
  2022). https://www.nature.com/articles/s41467-022-32552-1
  *Positioning:* The 125-gene signature we score with.

- **Tabula Muris Consortium, A single-cell transcriptomic atlas characterizes
  ageing tissues in the mouse** (Nature, 2020).
  https://www.nature.com/articles/s41586-020-2496-1
  *Positioning:* TMS — source of the mouse aging tissues and biological replicates
  used for the constructed-null demonstration.

- **GSE226225** — WI-38 human fibroblasts, experimentally induced senescence
  (CTRL/RS/IR/ETO). GEO accession.
  https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE226225
  *Positioning:* Ground-truth senescence labels for the true-positive / power-
  preservation half of the validation.

---

## Quick map: where each cluster sits relative to our claim

```
POPPER (§1)            governs error across a SEQUENCE of tests      ← one layer above
[ OUR CONTRIBUTION ]   validity of the statistical UNIT (pseudorep)  ← the open gap
EviBound (§1)          governs existence of test ARTIFACTS           ← one layer below

Single-cell agents (§2)   execute DE, no unit guardrail              ← the systems we audit
Pseudorep stats (§3)      the fix, for humans, not agents            ← the standard we enforce
Reliability benchmarks(§4) measure agent error, general not single-cell ← the crowding perimeter
Overclaiming (§5)         the problem, generalized                   ← our motivation
```
