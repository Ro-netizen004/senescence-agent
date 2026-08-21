# Confound-gate Functional Validation

**Status: paper candidate functional validation.**

The production admissibility gate was evaluated on five paired metadata challenges across 30 unique TMS Spleen B-cell donor allocations (150 decisions total).

| Challenge | n | Endpoint | Result |
|---|---:|---|---:|
| confounded | 30 | recall | 100% |
| confounded_partial | 30 | allow_rate | 100% |
| covariate_balanced | 30 | specificity | 100% |
| contrast_alias | 30 | allow_rate | 100% |
| contrast_alias_with_batch | 30 | recall | 100% |

Partial-confound warnings were issued in 30/30 cases; registered-alias warnings were issued in 30/30 cases. There were no unrelated blocks.

No LLM or DESeq2 calls were made. The same donor allocations are reused across synthetic challenge types; this is functional validation, not independent-cohort evidence.
