# OneK1K Full-agent Null Validation

**Status: paper-candidate agent-level calibration result.**

Ten registered classical-monocyte donor splits were run through matched governed and ungoverned agents. Each arm independently routed to and executed donor-level pseudobulk DESeq2 with `pool + sex + age + null_group`.

| Endpoint | Result |
|---|---:|
| Matched agent pairs | 10/10 |
| Correct routing, both arms | 20/20 |
| Governed plans accepted | 10/10 |
| Exact statistical parity | 10/10 |
| Registered zero-discovery result reproduced | 20/20 |
| Governed `NOT_SIGNIFICANT` state | 10/10 |
| Explicit null communication, governed | 10/10 |
| Explicit null communication, ungoverned | 10/10 |
| Positive significance claims, either arm | 0/20 |

This upgrades the OneK1K null from a method-only result to a full-agent routing, execution, and communication validation. It is not evidence of a governance withholding advantage: all underlying analyses had zero discoveries, so both arms had a straightforward null to report. The ten allocations reuse one donor cohort.

pyDESeq2 emitted overflow/invalid-value optimizer warnings, but all fits completed, every matched pair had an identical statistical signature, and all 20 results reproduced the registered zero-discovery count.
