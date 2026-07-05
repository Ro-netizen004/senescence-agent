"""
Null-harness sweep: run the gene-level pseudoreplication experiment across
multiple TMS tissues and cell types with many permutations, then aggregate a
single summary table for the paper.

Usage:
    python eval/ablation/run_null_sweep.py                 # defaults: 200 perms, top 3 cell types/tissue
    python eval/ablation/run_null_sweep.py --n-perm 500 --top 2

Outputs (per run, preserved):
    eval/results/ablation/null_<tissue>_<celltype>.json / .md
Aggregate:
    eval/results/ablation/null_sweep_summary.csv
    eval/results/ablation/null_sweep_summary.md
"""

import sys
import argparse
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd

from null_harness import run, MIN_CELLS_PER_SAMPLE

DATA_DIR = ROOT / "backend" / "data"
OUT_DIR = ROOT / "eval" / "results" / "ablation"

# TMS tissue files to sweep (only those present are used).
TISSUES = [
    "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Liver.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Spleen.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Aorta.h5ad",
    "tabula-muris-senis-facs-processed-official-annotations-Limb_Muscle.h5ad",
]

MIN_MICE = 4  # need >=4 replicates to form two groups


def _candidate_cell_types(path: Path, top: int) -> list[str]:
    """Backed obs-only read to rank cell types by # mice with enough cells."""
    import scanpy as sc
    ad = sc.read_h5ad(str(path), backed="r")
    obs = ad.obs
    ct_col = "cell_ontology_class" if "cell_ontology_class" in obs.columns else "cell_type"
    sample_col = "mouse.id" if "mouse.id" in obs.columns else "sample_id"
    counts = obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
    mice_ge = (counts >= MIN_CELLS_PER_SAMPLE).sum(axis=1)
    keep = mice_ge[mice_ge >= MIN_MICE].sort_values(ascending=False)
    try:
        ad.file.close()
    except Exception:
        pass
    return keep.index[:top].tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-perm", type=int, default=200)
    ap.add_argument("--top", type=int, default=3, help="cell types per tissue")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows = []
    for fname in TISSUES:
        path = DATA_DIR / fname
        if not path.exists():
            print(f"SKIP (missing): {fname}")
            continue

        tissue = fname.split("annotations-")[-1].replace(".h5ad", "")
        try:
            cell_types = _candidate_cell_types(path, args.top)
        except Exception as e:
            print(f"SKIP {tissue}: could not read cell types ({e})")
            continue

        print(f"\n{'#'*60}\n# {tissue}: {cell_types}\n{'#'*60}")
        for ct in cell_types:
            print(f"\n>>> {tissue} / {ct}")
            try:
                res = run(path, ct, args.n_perm, args.seed, None)
            except SystemExit:
                print(f"    skipped ({ct}: insufficient replicates)")
                continue
            except Exception as e:
                print(f"    error on {ct}: {e}")
                continue

            l1 = res["layer1_false_positive_genes"]
            l2 = res["layer2_agent_claim_rate"]
            rows.append({
                "tissue": tissue,
                "cell_type": ct,
                "n_mice": res["n_biological_replicates"],
                "n_genes": res["n_genes_tested"],
                "n_perm": res["n_permutations_valid"],
                "percell_fp_fdr_mean": l1["per_cell_fdr"]["mean"],
                "pseudobulk_fp_fdr_mean": l1["pseudobulk_fdr"]["mean"],
                "ungoverned_fdr_rate": l2["ungoverned_false_discovery_rate"],
                "governed_fdr_rate": l2["governed_false_discovery_rate"],
            })

    if not rows:
        print("\nNo runs completed.")
        return

    df = pd.DataFrame(rows)
    csv_path = OUT_DIR / "null_sweep_summary.csv"
    df.to_csv(csv_path, index=False)

    lines = [
        "# Null Harness Sweep - Summary",
        "",
        f"Configurations: {len(df)} | permutations each: {args.n_perm}",
        "",
        "| Tissue | Cell type | Mice | Genes | Per-cell FP (FDR) | Pseudobulk FP (FDR) | Ungoverned FDR rate | Governed FDR rate |",
        "|--------|-----------|-----:|------:|------------------:|--------------------:|--------------------:|------------------:|",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| {r['tissue']} | {r['cell_type']} | {r['n_mice']} | {r['n_genes']} | "
            f"**{r['percell_fp_fdr_mean']:.0f}** | {r['pseudobulk_fp_fdr_mean']:.1f} | "
            f"{r['ungoverned_fdr_rate']:.0%} | {r['governed_fdr_rate']:.0%} |"
        )
    lines += [
        "",
        f"**Mean per-cell false-positive genes (FDR): {df['percell_fp_fdr_mean'].mean():.0f}**",
        f"**Mean pseudobulk false-positive genes (FDR): {df['pseudobulk_fp_fdr_mean'].mean():.2f}**",
        "",
        "Truth = 0 DE genes (constructed null). Per-cell = ungoverned; pseudobulk = governed.",
    ]
    (OUT_DIR / "null_sweep_summary.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'='*60}\nSWEEP COMPLETE")
    print(f"Saved: {csv_path}")
    print(f"Saved: {OUT_DIR / 'null_sweep_summary.md'}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
