"""
Generate a NULL .h5ad for the CellAgent experiment.

Builds a genuinely null two-group dataset (same real age + sex mice, randomly
split) so that any differentially expressed gene CellAgent reports is a false
positive. Small file, ready to upload to Colab.

Usage:
    python eval/ablation/make_cellagent_null.py
    python eval/ablation/make_cellagent_null.py --cell-type "hepatocyte" --data <path> --seed 1
"""

import sys
import argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
import scanpy as sc

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
from agent.pipeline import ensure_pipeline

OUT_DIR = ROOT / "eval" / "results" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DATA = ROOT / "backend" / "data" / "tabula-muris-senis-facs-processed-official-annotations-Kidney.h5ad"
MIN_CELLS = 20


def _sex(mouse_id: str) -> str:
    s = str(mouse_id).rsplit("_", 1)[-1].upper()
    return s if s in ("M", "F") else "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default=str(DEFAULT_DATA))
    ap.add_argument("--cell-type", type=str, default="")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=str, default=str(OUT_DIR / "cellagent_null.h5ad"))
    args = ap.parse_args()

    adata = sc.read_h5ad(args.data)
    ensure_pipeline(adata, "mouse")
    prof = adata.uns.get("dataset_profile") or {}
    ct_col = prof.get("cell_type_column") or "cell_ontology_class"
    sample_col = prof.get("sample_column") or "sample_id"
    age_col = prof.get("age_column") or "age"

    cell_type = args.cell_type
    if not cell_type:
        counts = adata.obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
        cell_type = (counts >= MIN_CELLS).sum(axis=1).sort_values(ascending=False).index[0]

    sub = adata[adata.obs[ct_col].astype(str) == str(cell_type)].copy()
    vc = sub.obs[sample_col].astype(str).value_counts()
    mice = sorted(vc[vc >= MIN_CELLS].index.tolist())

    # homogeneous (age, sex) stratum with >= 4 mice
    m_age = {m: str(sub.obs.loc[sub.obs[sample_col].astype(str) == m, age_col].iloc[0]) for m in mice}
    m_sex = {m: _sex(m) for m in mice}
    strata = defaultdict(list)
    for m in mice:
        strata[(m_age[m], m_sex[m])].append(m)
    pools = sorted([v for v in strata.values() if len(v) >= 4], key=len, reverse=True)
    if not pools:
        raise SystemExit(f"No same-age same-sex stratum with >=4 mice for {cell_type}. "
                         f"Strata: { {k: len(v) for k, v in strata.items()} }")
    pool = pools[0]
    stratum = f"{m_age[pool[0]]} / sex {m_sex[pool[0]]}"

    rng = np.random.default_rng(args.seed)
    perm = list(rng.permutation(pool))
    half = len(perm) // 2
    A, B = set(perm[:half]), set(perm[half:2 * half])

    out = sub[sub.obs[sample_col].astype(str).isin(A | B)].copy()
    out.obs["group"] = np.where(out.obs[sample_col].astype(str).isin(list(A)), "groupA", "groupB")
    # keep obs minimal + clear for CellAgent
    out.obs = out.obs[[sample_col, "group"]].copy()
    out.obs["group"] = out.obs["group"].astype("category")

    out.write_h5ad(args.out)
    print(f"Cell type: {cell_type}")
    print(f"Homogeneous stratum (genuine null): {stratum}, {len(pool)} mice")
    print(f"  groupA mice: {sorted(A)}")
    print(f"  groupB mice: {sorted(B)}")
    print(f"  cells: {out.n_obs}, genes: {out.n_vars}")
    print(f"TRUTH: no real difference. Any DE gene CellAgent reports is a FALSE POSITIVE.")
    print(f"\nSaved: {args.out}  ({Path(args.out).stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
