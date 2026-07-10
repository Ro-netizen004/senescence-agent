import re
import numpy as np
import pandas as pd

from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats


def _extract_months(age_str):
    """
    Convert '3m', '24m' → 3, 24
    """
    match = re.findall(r"\d+", str(age_str))
    return int(match[0]) if match else None


def run_deseq2_pseudobulk(
    count_df,
    meta_df,
    design="age",
    reference_age=None,
    comparison_age=None,
):
    """
    DESeq2 pseudobulk with automatic young vs old contrast selection
    """

    meta_df = meta_df.copy()
    meta_df["age"] = meta_df["age"].astype(str)

    # =========================
    # Normalize age column
    # =========================
    meta_df["age_numeric"] = meta_df["age"].apply(_extract_months)

    available_ages = meta_df["age"].dropna().unique().tolist()

    # =========================
    # Detect or validate contrast
    # =========================
    if reference_age and comparison_age:
        # Explicit groups given (any labels, e.g. "control"/"senescent") -> no age parsing needed.
        youngest_label = str(reference_age)
        oldest_label = str(comparison_age)

        missing = [
            age for age in (youngest_label, oldest_label)
            if age not in available_ages
        ]
        if missing:
            raise ValueError(
                f"Requested age group(s) not found: {missing}. "
                f"Available age groups: {available_ages}"
            )
    else:
        # Auto-detect youngest/oldest requires numeric ages like '3m', '24m'.
        if meta_df["age_numeric"].isna().all():
            raise ValueError("Could not parse age values (expected formats like '3m', '24m')")
        youngest = meta_df["age_numeric"].min()
        oldest = meta_df["age_numeric"].max()

        youngest_label = meta_df.loc[
            meta_df["age_numeric"] == youngest, "age"
        ].iloc[0]

        oldest_label = meta_df.loc[
            meta_df["age_numeric"] == oldest, "age"
        ].iloc[0]

    print(f"[DESeq2] Youngest group: {youngest_label}")
    print(f"[DESeq2] Oldest group: {oldest_label}")

    # =========================
    # Filter to only young + old
    # =========================
    keep_samples = meta_df[
        meta_df["age"].isin([youngest_label, oldest_label])
    ].index

    count_df = count_df.loc[keep_samples]
    meta_df = meta_df.loc[keep_samples]

    # =========================
    # Drop low-count genes (standard pyDESeq2 practice) — avoids testing
    # tens of thousands of all-zero genes, which is slow and inflates FDR.
    # =========================
    gene_totals = count_df.sum(axis=0)
    count_df = count_df.loc[:, gene_totals >= 10]

    # =========================
    # Build DESeq2 dataset
    # =========================
    dds = DeseqDataSet(
        counts=count_df,
        metadata=meta_df,
        design_factors=design
    )

    dds.deseq2()

    # =========================
    # Proper contrast (IMPORTANT FIX)
    # =========================
    stat_res = DeseqStats(
        dds,
        contrast=[design, oldest_label, youngest_label]
    )

    stat_res.summary()

    results = stat_res.results_df.sort_values("padj")

    return {
        "results": results,
        "youngest_group": youngest_label,
        "oldest_group": oldest_label
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
