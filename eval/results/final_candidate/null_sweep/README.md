# Legacy Method-plus-Governance Null Pilot

**Historical after the same-method ablation redesign.** This package compares
governed pseudobulk DESeq2 with an ungoverned per-cell Wilcoxon implementation.
It remains useful as a full-system comparison but cannot attribute differences
to governance alone. Its replacement writes to `../null_sweep_same_method/`.

This directory holds the version-controlled protocol, seed definition,
aggregate results, and raw-artifact manifest for the final null evaluation.

Raw per-seed JSON and log files belong under `raw/`. That directory is ignored
by Git and must be preserved locally until it is archived in a versioned
research repository. Do not delete local raw results until the archive checksum
and manifest have been verified.

## Files retained in Git

- `protocol.json`: frozen experiment design and code provenance
- `seeds.txt`: pre-registered paired random seeds
- `raw_results_manifest.csv`: filename, seed, tissue, arm, status, and SHA-256
- aggregate CSV/JSON/Markdown summaries produced from the raw runs

## Pairing rule

Governed and ungoverned arms must use the same dataset subset and seed for each
paired comparison. A seed must not be replaced because its result is
unfavorable. Failed jobs remain in the manifest with their failure status and
may be rerun only with the same seed after documenting the technical cause.

## Publication boundary

The memory-safe evaluation harness is frozen at
`19799611bf7f8e64fed16873d96c7a094e891844`. This package remains a final
candidate until every expected paired run is represented in the manifest and
aggregate values reconcile to the raw archive.
