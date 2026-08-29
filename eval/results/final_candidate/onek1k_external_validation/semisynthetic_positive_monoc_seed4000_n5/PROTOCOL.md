# Protocol and Provenance

- Protocol: `onek1k_semisynthetic_v2`
- Protocol ID: `3b8bc3939e9fb710c1079bde7bafd82a3cbb06d609000760e2fcbbcd7110de02`
- Seeds: 4000-4004
- Dataset: `OneK1K_updated_14_celltypes_980_donors.h5ad`
- Zenodo record: https://zenodo.org/records/18870747
- Version DOI: `10.5281/zenodo.18870747`
- Dataset MD5: `a16487819c21506b400cd1d36f09c3e1`
- Cell type: `cell_label == "Mono C"`
- Minimum cells per donor: 20
- Eligible donors: 524
- Retained per allocation: 454, 227 per group
- Matching: exact pool/sex strata, adjacent ages
- DESeq2 design: `pool + sex + null_group`
- Registered effects: 25 genes per absolute log2FC tier 0.25, 0.50, 1.00; balanced up/down
- Significance threshold: Benjamini-Hochberg FDR < 0.05
- Governance: production admissibility, result plausibility, leave-one-donor-out stability, inference-state assignment
- LLM API calls: 0
- Base Git revision: `ab11f8ffbb037ebf235be85382d96e2d847ae09d`
- Exact benchmark script SHA-256: `1e8c7d136cbb1447b7214652eed568c35a530ad80ea0ba5bfe72c20a3a634aea`
- Packaged: 2026-08-29

The source H5AD is excluded from Git. Raw package records replace the local source path with the registered dataset filename. Per-allocation files are atomic checkpoints emitted by `eval/external_validation/onek1k/semisynthetic_benchmark.py`.
