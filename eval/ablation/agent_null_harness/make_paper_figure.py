"""Generate the manuscript figure from the frozen paired-paper summary."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "eval/results/final_candidate/null_sweep_same_method"


def main() -> None:
    summary = json.loads((PACKAGE / "paper_summary.json").read_text(encoding="utf-8"))
    tissue_rows = summary["tissue_results"]
    labels = [row["tissue"].replace("_", " ") for row in tissue_rows] + ["Pooled"]
    governed = [row["governed_reply_overclaim_rate"] for row in tissue_rows]
    ungoverned = [row["ungoverned_reply_overclaim_rate"] for row in tissue_rows]
    governed.append(summary["pooled"]["governed_reply_overclaim_rate"])
    ungoverned.append(summary["pooled"]["ungoverned_reply_overclaim_rate"])

    y = np.arange(len(labels))
    height = 0.34
    fig, ax = plt.subplots(figsize=(7.2, 4.2), constrained_layout=True)
    ax.barh(y - height / 2, governed, height, color="#26766f", label="Governed")
    ax.barh(y + height / 2, ungoverned, height, color="#c4523b", label="Ungoverned")
    ax.axhline(len(labels) - 1.5, color="#777777", linewidth=0.8)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.05)
    ax.set_xticks(np.linspace(0, 1, 6), [f"{value:.0%}" for value in np.linspace(0, 1, 6)])
    ax.set_xlabel("Reply overclaim rate across matched null allocations")
    ax.set_title("Governance suppresses unsupported significance claims", pad=34)
    ax.legend(
        frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.045),
        ncol=2, columnspacing=1.5,
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color="#dddddd", linewidth=0.7)
    ax.set_axisbelow(True)

    for values, offset in ((governed, -height / 2), (ungoverned, height / 2)):
        for index, value in enumerate(values):
            ax.text(
                min(value + 0.018, 1.01), index + offset, f"{value:.0%}",
                va="center", ha="left", fontsize=8.5,
            )

    caption = (
        "Same donor allocations and pseudobulk DESeq2 outputs in both arms; "
        "n=78 allocations. Allocation-level rates are descriptive because donors are reused."
    )
    fig.text(0.01, -0.025, caption, fontsize=8, color="#444444")
    for suffix in ("png", "pdf"):
        fig.savefig(PACKAGE / f"figure_overclaim_by_tissue.{suffix}", dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
