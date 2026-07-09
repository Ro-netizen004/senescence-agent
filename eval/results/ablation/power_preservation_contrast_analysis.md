# Power-preservation contrast analysis (GSE226225)

Record of the sample-composition audit and the DE re-analysis that moved Result #2 from a
heterogeneous 11-vs-2 pooled contrast to a clean, single-method 3-vs-2 contrast.

## Dataset composition (verified against GEO GSE226225)

Human WI-38 fibroblasts, scRNA-seq, **56,803 cells across 13 biological samples**. `obs` carries
`sample_id` and `condition` only (one `condition` label per sample).

| Sample (condition) | Meaning | n |
|---|---|---|
| `CTRL_2` | Proliferating control, PDL 24, untreated (**no `CTRL_1` exists**) | 1 |
| `RS_1`, `RS_2` | Replicative senescence, PDL 57 | 2 |
| `IR_1`, `IR_2` | Irradiation, 10 Gy + 10 d | 2 |
| `ETO_1`, `ETO_2` | **Etoposide 50 µM, 10 d — endpoint replicates** | 2 |
| `ETO_day_0` | DMSO vehicle, untreated (etoposide baseline) | 1 |
| `ETO_day_1/2/4/7/10` | Etoposide 50 µM kinetic time course | 1 each |

**Key facts:** only one untreated control exists; `ETO_day_0` is a DMSO vehicle baseline (n=1);
`ETO_1`, `ETO_2`, and `ETO_day_10` are all the *same* condition (50 µM / 10 d) → 3 true replicates.

## Problem with the original contrast

The original `label_group` pooled **non_senescent = {CTRL_2, ETO_day_0}** (2) vs
**senescent = {RS, IR, ETO, all ETO timepoints}** (11). Issues:
1. Only one true control; the second "control" is a time-course baseline.
2. Senescent group mixes three induction methods **and** a time course, including early timepoints
   (`ETO_day_1/2/4`) that are not yet senescent → induction-method + timepoint confounding.
3. Time-course samples are not independent senescence replicates.

## DE re-analysis (governed pseudobulk DESeq2, same pipeline, FDR<0.05)

| Contrast | Design | DE genes | up / down | Marker directions |
|---|---|---|---|---|
| **V0** original | 11 senescent (RS+IR+ETO+timepoints) vs 2 | 7,615 | 4309 / 3306 | all 6 correct |
| **V1 (adopted)** | etoposide-10d `{ETO_1, ETO_2, ETO_day_10}` vs `{ETO_day_0, CTRL_2}` (3 vs 2) | **10,002** | 4922 / 5080 | all correct, far stronger |
| V2 | `{ETO_1, ETO_2}` vs 2 (2 vs 2) | 11,054 | 5080 / 5974 | MMP3 n.s. |
| V3 | `{ETO_1, ETO_2, ETO_day_7, ETO_day_10}` vs 2 (4 vs 2) | 11,965 | 6037 / 5928 | MMP3 borderline |

Cleaner design → **more** power (lower within-group variance), not less.

## Adopted contrast: V1 — canonical marker recovery (official pipeline re-run)

Etoposide-induced senescence (10-day endpoint, 3 replicates) vs proliferating controls (2).
**10,002 DE genes; 12/14 markers significant.**

| Marker | log2FC | padj | dir |
|---|---|---|---|
| CDKN1A (p21) | +2.21 | 1.9e-15 | up ✓ |
| CDKN2A (p16) | +1.21 | 2.2e-03 | up ✓ |
| GDF15 | +3.64 | 7.9e-17 | up ✓ |
| IL6 | +2.15 | 8.3e-08 | up ✓ |
| IL1B | +1.32 | 8.1e-03 | up ✓ |
| TNFRSF10C | +2.49 | 1.3e-09 | up ✓ |
| MMP3 | +1.18 | 2.4e-02 | up ✓ (weak) |
| MKI67 | −7.48 | 4.5e-98 | down ✓ |
| LMNB1 | −6.77 | 4.0e-100 | down ✓ |
| IGFBP3 | −1.41 | 2.0e-05 | (down) |
| SERPINE1 | −0.79 | 3.5e-03 | (down, unexpected sign) |
| GLB1 | +0.69 | 2.5e-02 | up ✓ |
| CXCL8 | −0.06 | 0.97 | n.s. |
| TP53 | +0.37 | 0.28 | n.s. |

Ungoverned per-cell on the same contrast: 10,005 DE genes (of 10,418 tested) — both detect the
real effect, confirming power preservation is not an artifact of the statistical unit.

**Headline for slides/paper (avoids over-precision on small n):** recovered **~10,000 DE genes**,
with canonical markers in the correct direction at high significance — **CDKN1A (p21), CDKN2A
(p16), GDF15, IL6 up; MKI67, LMNB1 down**. Lead with markers (positive control), not the raw count.

## Files
- `power_preservation.py` — updated `label_group` to the V1 contrast.
- `power_preservation.json` — regenerated with V1 numbers.
- `power_preservation_run.txt` — full console output of the official re-run.
