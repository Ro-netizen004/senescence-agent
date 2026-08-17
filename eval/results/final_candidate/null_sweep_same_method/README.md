# Same-method Governance Ablation

This directory is the destination for the paper-facing governance pilot. Both
arms run donor-level pseudobulk DESeq2 on identical donor allocations with
identical contrasts, design factors, and covariates.

The paired aggregator rejects output when any of these differ:

- allocation ID;
- raw significant-gene count;
- significant-gene identity;
- DESeq2 design factors;
- covariates used or dropped.

Runs use the protected arm names `governed_same_method` and
`ungoverned_same_method`, so historical per-cell outputs cannot be overwritten.
After both arms finish, `build_paired_paper_results.py` creates the paper tables,
manifest, checksums, and rescore audit here.
