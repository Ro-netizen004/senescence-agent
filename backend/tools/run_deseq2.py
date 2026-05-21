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

    if meta_df["age_numeric"].isna().all():
        raise ValueError("Could not parse age values (expected formats like '3m', '24m')")

    available_ages = meta_df["age"].dropna().unique().tolist()

    # =========================
    # Detect or validate contrast
    # =========================
    if reference_age and comparison_age:
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
