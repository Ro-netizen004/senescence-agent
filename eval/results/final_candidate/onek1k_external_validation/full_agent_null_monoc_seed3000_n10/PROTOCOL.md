# Frozen Protocol

- Dataset: `OneK1K_updated_14_celltypes_980_donors.h5ad`
- Source: Zenodo `10.5281/zenodo.18870747`; MD5 `a16487819c21506b400cd1d36f09c3e1`
- Population: `Mono C`; seeds 3000-3009; 454 donors per allocation (227 per group)
- Prompt: `Run differential expression on Mono C between fake_A and fake_B using null_group as the grouping variable and sample_id as the biological replicate, adjusting for pool, sex, and age.`
- Design: `pool + sex + age + null_group`; biological unit: donor (`sample_id`)
- Arms independently execute production donor-level pseudobulk DESeq2
- Adapter: 20 rows per donor, losslessly reconstructing registered pseudobulk counts
- Checkpoint: one seed/arm; model recorded in raw checkpoints
- Evaluated base revision: `e4f5d6055c7a1400e696470b50e7362843c447fc`
- Full-agent harness SHA-256: `2ec928854f2d3f7b325e9c54b5a82fb41a2a35314177734561e4438a2e28c79f`
- Saved replies were rescored offline after a zero-count matcher regression fix; no API or DE calls were repeated
