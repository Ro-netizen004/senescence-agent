## Same-method governance ablation

We evaluated whether the governance layer prevented unsupported significance
claims under constructed donor-level null contrasts while holding the
statistical analysis constant. The governed and ungoverned agents received
identical age- and sex-stratified donor allocations and used identical
pseudobulk DESeq2 outputs. Exact parity was required for allocation identity,
significant-gene sets, discovery counts, design factors, and covariate handling.

Across 78 matched allocations spanning five Tabula Muris Senis tissue and cell
type combinations, both arms produced the same mean number of raw null
discoveries (132.81 per allocation). The governed agent made no unsupported
significance claims (0/78; 0%), whereas the ungoverned agent overclaimed in
72/78 allocations (92.3%). The corresponding allocation-level Wilson intervals
were 0-4.7% and 84.2-96.4%, respectively. The governed agent withheld
gene-level results in all allocations (78/78), compared with 4/78 allocations
for the ungoverned agent.

The effect was observed across all five evaluated settings: ungoverned
overclaim rates were 100% in kidney, 62.5% in liver, 90% in spleen, 100% in
aorta, and 100% in limb muscle, while governed overclaim was 0% in every
setting. Because the same DESeq2 results were supplied to both arms, this
difference reflects inference governance rather than a change in the
underlying differential-expression method.

These results constitute a multi-tissue pilot rather than independent
population-level replication. The 78 allocations reuse a limited set of TMS
donors, and raw discoveries under constructed labels are not asserted to be
gene-level ground-truth false positives. External validation in a many-donor
droplet/UMI cohort is therefore required.

**Figure caption.** Reply overclaim rates for governed and ungoverned agents
across matched donor-split null allocations. Both arms used the same donor-level
pseudobulk DESeq2 analysis and were required to match exactly on allocation and
statistical output. The pooled analysis contains 78 allocations. Rates and
Wilson intervals are allocation-level descriptive summaries because donors are
reused across allocations.
