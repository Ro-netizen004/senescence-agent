# Frozen Protocol

- Dataset: `OneK1K_updated_14_celltypes_980_donors.h5ad`
- Source: Zenodo record `18870747`; version DOI `10.5281/zenodo.18870747`
- Dataset MD5: `a16487819c21506b400cd1d36f09c3e1`
- Cell population: `Mono C` (classical monocytes)
- Seeds: 4000-4004
- Donors per allocation: 454 (227 per group)
- Registered effects: 75 per allocation at absolute log2FC 0.25, 0.50, 1.00
- Prompt: `Run differential expression on Mono C between inject_A and inject_B using null_group as the grouping variable and sample_id as the biological replicate, adjusting for pool and sex.`
- Arms: governed production and ungoverned evaluation ablation
- Both arms independently execute production donor-level pseudobulk DESeq2
- Covariates: `pool`, `sex`
- Checkpoint unit: one seed/arm
- LLM model: recorded in each raw checkpoint
- Evaluated base Git revision: `c3a6ec01d86e8ab109aa1dac98450aacf9b08a5a`
- Exact full-agent harness SHA-256: `799e26daad466fb472497ffc10af7517fd0a8f0e2bb023eb9f02cbfc526f1594`
- Production route: deterministic validated route plus LLM analysis-plan proposal
- Ungoverned route: LLM tool selection and LLM narration
- Evaluation adapter: 20 rows per donor; one row carries the donor count vector and 19 are zero; production aggregation reconstructs the exact registered donor counts
