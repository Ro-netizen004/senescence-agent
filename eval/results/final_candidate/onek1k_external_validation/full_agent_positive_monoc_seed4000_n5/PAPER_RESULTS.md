# OneK1K Full-agent Semi-synthetic Positive Control

**Status: paper-candidate agent-level selectivity result.**

Five registered OneK1K classical-monocyte allocations were run through both the
governed production agent and the ungoverned ablation. Each arm independently
routed to and executed donor-level pseudobulk DESeq2 with `pool + sex +
null_group`; no frozen statistical output was supplied to the agent.

| Endpoint | Result |
|---|---:|
| Matched agent pairs | 5/5 |
| Correct `run_deseq2` routing, governed | 5/5 |
| Correct `run_deseq2` routing, ungoverned | 5/5 |
| Governed LLM plans accepted | 5/5 |
| Exact statistical parity between arms | 5/5 |
| Registered discovery-count reproduction, both arms | 10/10 |
| Governed `SIGNIFICANT_INFERENTIAL` | 5/5 |
| Governed replies communicating signal | 5/5 |
| Ungoverned replies communicating signal | 5/5 |
| Registered effects recovered | 358/375 (95.47%) |

Per-seed discovery counts were 76, 72, 74, 72, and 75 (mean 73.8). This closes
the evaluation asymmetry: the governed agent withheld unsupported null findings
in the matched TMS experiment but did not behave as a blanket refusal system on
valid, donor-stable injected signal.

## Interpretation boundary

The production agent received a lossless AnnData evaluation adapter in which
each donor's registered pseudobulk count vector was reconstructed exactly by the
production pseudobulk builder. Thus routing, LLM planning, admissibility, DESeq2
execution, inference-state assignment, and communication were exercised. Raw-cell
upload and upstream OneK1K aggregation were performed once by the registered
memory-safe builder rather than repeated independently in every arm.

pyDESeq2 emitted overflow/invalid-value warnings during optimization. The result
is retained because all ten fits completed, every governed/ungoverned pair had
an identical statistical signature, and all ten reproduced the previously
frozen per-seed discovery count.
