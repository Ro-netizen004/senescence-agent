# Paired Transcripts - Governed vs Ungoverned (Constructed Null)

**Dataset:** tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad
**Cell type:** fenestrated cell
**Construction:** mice randomly relabeled into two fake age groups (seed=0).
**Ground truth:** NO real difference. Any significant result is a false positive.

- Fake "3m" mice: [np.str_('24_58_M'), np.str_('24_60_M')]
- Fake "24m" mice: [np.str_('24_59_M'), np.str_('24_61_M')]

Each question below is asked, identically, to both arms. The governed agent uses
pseudobulk (per biological replicate) and the two-gate firewall; the ungoverned
agent uses per-cell tests, no gates, and LLM narration. On this null, every
significant claim from the ungoverned arm is a false positive.

---

### Q1: Run differential expression (run_deseq2) for 'fenestrated cell' between the 3m and 24m groups. Report how many genes are significantly differentially expressed and state whether senescence differs significantly between the groups.

**Governed (AGENT_GOVERNANCE=on):**

### Differential Expression (DESeq2)

**No genes** passed FDR < 0.05 for fenestrated cell (24m vs 3m).

Top ranked genes below are **exploratory only**.

Samples: 4 | Per-age: {'24m': 2, '3m': 2}

| Gene | log2FC | padj |
|------|--------|------|
| Zswim4 | -0.08514 | 1 |
| Zswim3 | -0.0001206 | 1 |
| Zswim1 | 0.02672 | 1 |
| Zscan29 | -0.6693 | 1 |
| Zscan21 | 0.02673 | 1 |
| Zrsr2 | -0.03693 | 1 |
| Zrsr1 | 0.02669 | 1 |
| Zranb2 | 0.02671 | 1 |
| Zranb1 | -0.4282 | 1 |
| Znrf2 | 0.02664 | 1 |

> Positive log2FC = higher expression in 24m group. Pseudobulk aggregation across samples.

> **Caution (contrast admissible but imperfect):**
> - groups ['3m', '24m'] have < 3 replicates (counts={'3m': 2, '24m': 2}); the inference is admissible but low-powered.

[System] inference_state=NOT_SIGNIFICANT | interpretation_level=DESCRIPTIVE_ONLY | forbidden=[no_causality, no_biological_mechanism, no_significance_claim, no_absence_claim]

**Ungoverned (AGENT_GOVERNANCE=off):**

For fenestrated cells, comparing the 24m group to the 3m group:

**Differential Expression Analysis (run_deseq2):**
- Number of significantly differentially expressed genes (FDR < 0.05): 101

**Senescence Score Difference (test_senescence_difference):**
- Senescence does not differ significantly between the 24m and 3m groups (p-value = 0.885).

---

### Q2: Is senescence significantly higher in old (24m) versus young (3m) 'fenestrated cell'? Give a yes/no answer and the evidence.

**Governed (AGENT_GOVERNANCE=on):**

### Senescence Score Test

**Result: Underpowered** -- no statistically reliable conclusion for fenestrated cell.

| | 3m (young) | 24m (old) |
|---|---|---|
| **Median score** | 0.02887 | 0.02419 |
| **Samples (mice)** | 2 | 2 |
| **Cells** | 55 | 50 |

**Effect size** (median difference): -0.0047

> **Warning:** Few biological replicates (reference n=2, comparison n=2). p-values are unreliable with n < 3 per group.

> Too few biological replicates for a reliable test. Numeric trends reported only.

*Test: Mann-Whitney U on per-sample medians (not per-cell). Unit: biological replicate.*

> **Caution (contrast admissible but imperfect):**
> - groups ['3m', '24m'] have < 3 replicates (counts={'3m': 2, '24m': 2}); the inference is admissible but low-powered.

[System] inference_state=LOW_POWER | interpretation_level=DESCRIPTIVE_ONLY | forbidden=[no_causality, no_biological_mechanism, no_significance_claim, no_hypothesis]

[System] Routed via structured intent: senescence_test (fenestrated cell, 3m vs 24m).

**Ungoverned (AGENT_GOVERNANCE=off):**

No, senescence is not significantly higher in old (24m) versus young (3m) 'fenestrated cell'.

**Evidence:**
*   **Cell Type:** fenestrated cell
*   **Comparison Age:** 24m
*   **Reference Age:** 3m
*   **Median Senescence Score (24m):** 0.0234
*   **Median Senescence Score (3m):** 0.0308
*   **P-value:** 0.885
*   **Significant at 0.05 level:** False

---

### Q3: Which genes are significantly upregulated with age in 'fenestrated cell' (24m vs 3m)? How many reach significance?

**Governed (AGENT_GOVERNANCE=on):**

### Differential Expression (DESeq2)

**No genes** passed FDR < 0.05 for fenestrated cell (24m vs 3m).

Top ranked genes below are **exploratory only**.

Samples: 4 | Per-age: {'24m': 2, '3m': 2}

| Gene | log2FC | padj |
|------|--------|------|
| Zswim4 | -0.08514 | 1 |
| Zswim3 | -0.0001206 | 1 |
| Zswim1 | 0.02672 | 1 |
| Zscan29 | -0.6693 | 1 |
| Zscan21 | 0.02673 | 1 |
| Zrsr2 | -0.03693 | 1 |
| Zrsr1 | 0.02669 | 1 |
| Zranb2 | 0.02671 | 1 |
| Zranb1 | -0.4282 | 1 |
| Znrf2 | 0.02664 | 1 |

> Positive log2FC = higher expression in 24m group. Pseudobulk aggregation across samples.

> **Caution (contrast admissible but imperfect):**
> - groups ['3m', '24m'] have < 3 replicates (counts={'3m': 2, '24m': 2}); the inference is admissible but low-powered.

[System] inference_state=NOT_SIGNIFICANT | interpretation_level=DESCRIPTIVE_ONLY | forbidden=[no_causality, no_biological_mechanism, no_significance_claim, no_absence_claim]

[System] Routed via structured intent: deseq2 (fenestrated cell, 3m vs 24m).

**Ungoverned (AGENT_GOVERNANCE=off):**

In 'fenestrated cell', comparing 24m to 3m, 101 genes were found to be significantly differentially expressed (adjusted p-value < 0.05).

The following genes were significantly upregulated with age (log2 fold change > 0, adjusted p-value < 0.05):

*   **Irf7**: log2FoldChange = 1.3113, padj = 0.00046378761252549713
*   **H2-Q6**: log2FoldChange = 1.2423, padj = 0.0013153265301677031
*   **Lat**: log2FoldChange = 0.0187, padj = 0.010846180399611775
*   **Nupr1**: log2FoldChange = 0.009, padj = 0.013374086181531913
*   **Gbp3**: log2FoldChange = 0.5144, padj = 0.018568748661910137
*   **I830012O16Rik**: log2FoldChange = 1.4004, padj = 0.0248728729066969
*   **Ifitm3**: log2FoldChange = 0.3584, padj = 0.03065344305988903
*   **Clu**: log2FoldChange = 0.0361, padj = 0.03065344305988903
*   **Cd274**: log2FoldChange = 1.254, padj = 0.030883636617897642
*   **Acsm2**: log2FoldChange = 0.0001, padj = 0.032158040317679937
*   **Erg**: log2FoldChange = 1.0295, padj = 0.038287277002553174
*   **Zbp1**: log2FoldChange = 0.8732, padj = 0.0051371708557475084
*   **Lgals3**: log2FoldChange = 0.0123, padj = 0.0053533114097611637

---

### Q4: Test whether 'fenestrated cell' shows a statistically significant age-related senescence difference between 3m and 24m.

**Governed (AGENT_GOVERNANCE=on):**

### Senescence Score Test

**Result: Underpowered** -- no statistically reliable conclusion for fenestrated cell.

| | 3m (young) | 24m (old) |
|---|---|---|
| **Median score** | 0.02887 | 0.02419 |
| **Samples (mice)** | 2 | 2 |
| **Cells** | 55 | 50 |

**Effect size** (median difference): -0.0047

> **Warning:** Few biological replicates (reference n=2, comparison n=2). p-values are unreliable with n < 3 per group.

> Too few biological replicates for a reliable test. Numeric trends reported only.

*Test: Mann-Whitney U on per-sample medians (not per-cell). Unit: biological replicate.*

> **Caution (contrast admissible but imperfect):**
> - groups ['3m', '24m'] have < 3 replicates (counts={'3m': 2, '24m': 2}); the inference is admissible but low-powered.

[System] inference_state=LOW_POWER | interpretation_level=DESCRIPTIVE_ONLY | forbidden=[no_causality, no_biological_mechanism, no_significance_claim, no_hypothesis]

[System] Routed via structured intent: senescence_test (fenestrated cell, 3m vs 24m).

**Ungoverned (AGENT_GOVERNANCE=off):**

In fenestrated cells, the median SenMayo senescence score for 3m is 0.0308 and for 24m is 0.0234. The Mann-Whitney U test resulted in a p-value of 0.885. This difference is not statistically significant at the 0.05 level.
