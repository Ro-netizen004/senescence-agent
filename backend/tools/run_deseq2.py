import re
import numpy as np
import pandas as pd

from agent.design_validation import validate_factor_design

from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

# ── Gate 2: result-plausibility thresholds ──────────────────────────────────
# The admissibility gate checks the *design*; this checks whether the *result*
# has the fingerprints of a technical artifact rather than real biology.
_EXTREME_LFC = 8.0            # |log2FC| > 8 (256-fold) is biologically implausible
_IMPLAUSIBLE_MEDIAN_LFC = 5.0  # typical hit > 32-fold => effect sizes look technical
_EXTREME_FRAC_WARN = 0.30      # >30% of hits extreme => suspect
_DIRECTION_SKEW_WARN = 0.90    # >90% of hits one direction => systematic difference
_MIN_SIG_FOR_CHECK = 20        # too few hits to judge skew/fraction reliably

_STABILITY_MIN_SAMPLES_PER_GROUP = 4
_STABILITY_MIN_STABLE_GENE_FRACTION = 0.80
_STABILITY_MIN_EFFECT_RETENTION = 0.50


def assess_replicate_stability(
    count_df,
    meta_df,
    results_df,
    group_column,
    reference_group,
    comparison_group,
) -> dict:
    """Leave-one-donor-out effect stability for FDR-significant genes.

    This is a deterministic sensitivity analysis, not a second significance
    test. Effects are comparison-minus-reference differences on log2(CPM+1)
    pseudobulk profiles. Each donor is removed once without refitting DESeq2.
    """
    sig = results_df[
        results_df["padj"].fillna(1.0) < 0.05
    ] if "padj" in results_df.columns else results_df.iloc[0:0]
    genes = [g for g in sig.index if g in count_df.columns]
    groups = meta_df[group_column].astype(str)
    ref, comp = str(reference_group), str(comparison_group)
    contrast_samples = groups.index[groups.isin([ref, comp])]
    all_counts = count_df.loc[contrast_samples]
    counts = all_counts.loc[:, genes]
    groups = groups.loc[contrast_samples]
    per_group = {g: int((groups == g).sum()) for g in (ref, comp)}
    base = {
        "method": "leave-one-donor-out log2(CPM+1) effect stability",
        "n_significant_genes": len(genes),
        "samples_per_group": per_group,
        "thresholds": {
            "minimum_samples_per_group": _STABILITY_MIN_SAMPLES_PER_GROUP,
            "minimum_stable_gene_fraction": _STABILITY_MIN_STABLE_GENE_FRACTION,
            "minimum_effect_retention": _STABILITY_MIN_EFFECT_RETENTION,
            "direction_required_in_every_omission": True,
        },
    }
    if not genes:
        return base | {"verdict": "not_applicable", "reason": "no_significant_genes"}
    if min(per_group.values()) < _STABILITY_MIN_SAMPLES_PER_GROUP:
        return base | {
            "verdict": "insufficient_evidence",
            "reason": "fewer_than_4_samples_in_at_least_one_group",
        }

    library_sizes = all_counts.sum(axis=1).replace(0, np.nan)
    log_cpm = np.log2(counts.div(library_sizes, axis=0) * 1e6 + 1).fillna(0.0)

    def effect(frame, labels):
        return frame.loc[labels == comp].mean(axis=0) - frame.loc[labels == ref].mean(axis=0)

    full_effect = effect(log_cpm, groups)
    omitted_effects = []
    for sample in log_cpm.index:
        keep = log_cpm.index != sample
        omitted_effects.append(effect(log_cpm.loc[keep], groups.loc[keep]))
    loo = pd.DataFrame(omitted_effects, index=[str(s) for s in log_cpm.index])

    direction_stable = ((np.sign(loo) == np.sign(full_effect)).all(axis=0)) & (full_effect != 0)
    denominator = full_effect.abs().replace(0, np.nan)
    min_retention = loo.abs().min(axis=0).div(denominator).fillna(0.0)
    stable = direction_stable & (min_retention >= _STABILITY_MIN_EFFECT_RETENTION)
    details = []
    for gene in genes:
        details.append({
            "gene": str(gene),
            "full_log2cpm_effect": round(float(full_effect[gene]), 6),
            "direction_stable": bool(direction_stable[gene]),
            "minimum_effect_retention": round(float(min_retention[gene]), 4),
            "stable": bool(stable[gene]),
        })
    stable_fraction = float(stable.mean()) if len(stable) else 0.0
    return base | {
        "verdict": "stable" if stable_fraction >= _STABILITY_MIN_STABLE_GENE_FRACTION else "unstable",
        "n_stable_genes": int(stable.sum()),
        "stable_gene_fraction": round(stable_fraction, 4),
        "median_minimum_effect_retention": round(float(min_retention.median()), 4),
        "genes": details,
    }


def assess_de_plausibility(results_df) -> dict:
    """Flag DESeq2 results whose effect sizes look like a technical artifact
    (implausibly large fold-changes, or a near-uniform direction — the signature
    of library-size / low-count imbalance between groups). Does NOT block: the
    test may be statistically valid; this only cautions on interpretation.
    """
    df = results_df.dropna(subset=["padj", "log2FoldChange"])
    sig = df[df["padj"] < 0.05]
    n = int(len(sig))
    if n == 0:
        return {"verdict": "ok", "n_significant": 0, "reasons": []}

    lfc = sig["log2FoldChange"].astype(float)
    n_extreme = int((lfc.abs() > _EXTREME_LFC).sum())
    frac_extreme = n_extreme / n
    n_up = int((lfc > 0).sum())
    n_down = int((lfc < 0).sum())
    skew = max(n_up, n_down) / n
    median_abs = float(lfc.abs().median())

    reasons = []
    if n >= _MIN_SIG_FOR_CHECK and median_abs > _IMPLAUSIBLE_MEDIAN_LFC:
        reasons.append(
            f"the typical significant gene has |log2FC| = {median_abs:.1f} "
            f"(~{2 ** median_abs:,.0f}-fold); effect sizes this large across many "
            f"genes are usually a low-count / library-size artifact, not real regulation"
        )
    if n >= _MIN_SIG_FOR_CHECK and frac_extreme > _EXTREME_FRAC_WARN:
        reasons.append(
            f"{n_extreme}/{n} significant genes ({frac_extreme:.0%}) have "
            f"|log2FC| > {_EXTREME_LFC:.0f}"
        )
    if n >= _MIN_SIG_FOR_CHECK and skew > _DIRECTION_SKEW_WARN:
        direction = "down" if n_down > n_up else "up"
        reasons.append(
            f"{max(n_up, n_down)}/{n} significant genes ({skew:.0%}) move the same "
            f"direction ({direction}); a near-uniform direction points to a systematic "
            f"technical difference between the groups (e.g. library size or batch)"
        )

    return {
        "verdict": "suspect" if reasons else "ok",
        "n_significant": n,
        "n_extreme_lfc": n_extreme,
        "frac_extreme_lfc": round(frac_extreme, 3),
        "pct_up": round(100 * n_up / n, 1),
        "pct_down": round(100 * n_down / n, 1),
        "median_abs_log2fc": round(median_abs, 2),
        "extreme_lfc_threshold": _EXTREME_LFC,
        "reasons": reasons,
    }


def _extract_months(age_str):
    """
    Convert '3m', '24m' → 3, 24
    """
    match = re.findall(r"\d+", str(age_str))
    return int(match[0]) if match else None


def run_deseq2_pseudobulk(
    count_df,
    meta_df,
    group_column="age",
    reference_group=None,
    comparison_group=None,
    design=None,
    reference_age=None,
    comparison_age=None,
    covariates=None,
):
    """
    Pseudobulk DESeq2 between two groups of a grouping variable.

    The grouping variable can be anything sample-level: age, condition,
    treatment, genotype, etc. When ``reference_group``/``comparison_group`` are
    given they are used directly; otherwise — only for numeric age-like values
    like '3m'/'24m' — the youngest and oldest groups are auto-selected.

    Back-compat: ``design`` aliases ``group_column``; ``reference_age`` /
    ``comparison_age`` alias ``reference_group`` / ``comparison_group``.
    """

    group_column = design or group_column
    reference_group = reference_group or reference_age
    comparison_group = comparison_group or comparison_age

    meta_df = meta_df.copy()
    if group_column not in meta_df.columns:
        raise ValueError(
            f"Grouping column '{group_column}' not in pseudobulk metadata "
            f"(have: {list(meta_df.columns)})."
        )

    # Copy the chosen grouping column into a fixed, formula-safe factor name so
    # DESeq2's design never breaks on column names with spaces/dots.
    meta_df["_group"] = meta_df[group_column].astype(str)
    available_groups = meta_df["_group"].dropna().unique().tolist()

    # =========================
    # Detect or validate contrast
    # =========================
    if reference_group and comparison_group:
        ref_label = str(reference_group)
        comp_label = str(comparison_group)

        missing = [g for g in (ref_label, comp_label) if g not in available_groups]
        if missing:
            raise ValueError(
                f"Requested group(s) not found in '{group_column}': {missing}. "
                f"Available groups: {available_groups}"
            )
    else:
        # Auto-detect only works for numeric age-like values ('3m', '24m').
        meta_df["age_numeric"] = meta_df["_group"].apply(_extract_months)
        if meta_df["age_numeric"].isna().all():
            raise ValueError(
                f"Two groups to compare are required for '{group_column}'. "
                f"Available groups: {available_groups}. "
                f"Specify reference_group and comparison_group."
            )
        youngest = meta_df["age_numeric"].min()
        oldest = meta_df["age_numeric"].max()
        ref_label = meta_df.loc[meta_df["age_numeric"] == youngest, "_group"].iloc[0]
        comp_label = meta_df.loc[meta_df["age_numeric"] == oldest, "_group"].iloc[0]

    print(f"[DESeq2] grouping variable: {group_column}")
    print(f"[DESeq2] reference group: {ref_label}")
    print(f"[DESeq2] comparison group: {comp_label}")

    # =========================
    # Filter to only the two contrast groups
    # =========================
    keep_samples = meta_df[meta_df["_group"].isin([ref_label, comp_label])].index

    count_df = count_df.loc[keep_samples]
    meta_df = meta_df.loc[keep_samples]

    covariates = list(dict.fromkeys(covariates or []))
    design_validation = validate_factor_design(meta_df, group_column, covariates)

    # =========================
    # Drop low-count genes (standard pyDESeq2 practice) — avoids testing
    # tens of thousands of all-zero genes, which is slow and inflates FDR.
    # =========================
    gene_totals = count_df.sum(axis=0)
    count_df = count_df.loc[:, gene_totals >= 10]

    # =========================
    # Build DESeq2 dataset with optional sample-level adjustment covariates.
    # =========================
    design_factors = []
    covariates_used = []
    covariates_dropped = []
    for i, covariate in enumerate(covariates):
        if covariate not in meta_df.columns:
            raise ValueError(f"Covariate '{covariate}' missing from pseudobulk metadata")
        if meta_df[covariate].isna().any():
            raise ValueError(f"Covariate '{covariate}' contains missing sample values")
        if meta_df[covariate].astype(str).nunique() < 2:
            covariates_dropped.append({"column": covariate, "reason": "invariant"})
            continue
        safe = f"_covariate_{i}"
        meta_df[safe] = meta_df[covariate]
        design_factors.append(safe)
        covariates_used.append(covariate)
    design_factors.append("_group")

    dds = DeseqDataSet(
        counts=count_df,
        metadata=meta_df,
        design_factors=design_factors,
    )

    dds.deseq2()

    # =========================
    # Proper contrast: positive log2FC = higher in the comparison group.
    # =========================
    stat_res = DeseqStats(
        dds,
        contrast=["_group", comp_label, ref_label]
    )

    stat_res.summary()

    results = stat_res.results_df.sort_values("padj")

    return {
        "results": results,
        "group_column": group_column,
        "reference_group": ref_label,
        "comparison_group": comp_label,
        "design_factors": covariates_used + [group_column],
        "covariates_used": covariates_used,
        "covariates_dropped": covariates_dropped,
        "design_validation": design_validation,
        # Legacy keys (kept so existing callers/volcano labels keep working).
        "youngest_group": ref_label,
        "oldest_group": comp_label,
    }


def generate_volcano(results_df, out_dir, oldest="comparison", youngest="reference",
                     filename="volcano.png"):
    """Volcano plot from a DESeq2 results frame (index=gene; cols log2FoldChange, padj).
    Saves a PNG to out_dir and returns its path. Labels the strongest up/down genes."""
    import os
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    df = results_df.dropna(subset=["padj", "log2FoldChange"]).copy()
    if df.empty:
        return None
    df["nlp"] = -np.log10(df["padj"].clip(lower=1e-300))
    ymax = float(min(df["nlp"].max() * 1.05, 320)) or 1.0
    df["nlp"] = df["nlp"].clip(upper=ymax)
    sig = df["padj"] < 0.05
    up = sig & (df["log2FoldChange"] > 0)
    dn = sig & (df["log2FoldChange"] < 0)
    n_sig = int(sig.sum())

    plt.figure(figsize=(7, 5.5), dpi=150)
    plt.scatter(df.loc[~sig, "log2FoldChange"], df.loc[~sig, "nlp"], s=6, c="#CAD2D8", alpha=0.5, linewidths=0, label="not significant")
    plt.scatter(df.loc[up, "log2FoldChange"], df.loc[up, "nlp"], s=8, c="#006747", alpha=0.7, linewidths=0, label=f"up in {oldest}")
    plt.scatter(df.loc[dn, "log2FoldChange"], df.loc[dn, "nlp"], s=8, c="#B85042", alpha=0.7, linewidths=0, label=f"down in {oldest}")
    plt.axhline(-np.log10(0.05), ls="--", c="#7E96A0", lw=1)
    for g in list(df[up].sort_values("padj").head(4).index) + list(df[dn].sort_values("padj").head(4).index):
        row = df.loc[g]
        plt.annotate(str(g), (row["log2FoldChange"], row["nlp"]), fontsize=8.5, fontweight="bold",
                     color="#2B3B40", textcoords="offset points", xytext=(4, 3),
                     bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.8))
    plt.xlabel(f"log2 fold change  ({oldest} vs {youngest})", fontsize=11)
    plt.ylabel("-log10 adjusted p-value", fontsize=11)
    plt.title(f"Differential expression volcano\n{n_sig:,} genes at FDR < 0.05", fontsize=12, fontweight="bold", color="#006747")
    plt.legend(loc="upper center", fontsize=8, frameon=True, framealpha=0.9, markerscale=2)
    plt.tight_layout()
    path = os.path.join(out_dir, filename)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    return path
