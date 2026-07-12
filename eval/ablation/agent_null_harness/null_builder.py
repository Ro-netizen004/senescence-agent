"""
Construct null datasets for agent-level evaluation.

Truth = 0 differentially expressed genes: whole mice are randomly relabeled
into fake age groups within one cell type (Squair et al. 2021 construction).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

MIN_CELLS_PER_SAMPLE = 20
FAKE_YOUNG = "3m"
FAKE_OLD = "24m"


def _mouse_sex(mouse_id: str) -> str:
    suffix = str(mouse_id).rsplit("_", 1)[-1].upper()
    return suffix if suffix in ("M", "F") else "?"


def _usable_mice(sub, ct_col: str, sample_col: str, cell_type: str) -> list[str]:
    import scanpy as sc  # noqa: F401 — ensure scanpy-backed obs types work

    cells = sub[sub.obs[ct_col].astype(str) == str(cell_type)]
    vc = cells.obs[sample_col].astype(str).value_counts()
    return sorted(vc[vc >= MIN_CELLS_PER_SAMPLE].index.tolist())


def build_null_adata(
    data_path: Path,
    cell_type: str,
    seed: int,
    *,
    mode: str = "homogeneous",
):
    """
    Build a one-cell-type AnnData object with fake 3m/24m labels.

    Parameters
    ----------
    mode:
        ``homogeneous`` — split mice from the largest same-age-and-sex stratum
        (paired-transcripts style; removes real age/sex signal).
        ``random`` — split all usable mice at random (null-harness style).
    """
    import scanpy as sc
    from agent.pipeline import ensure_pipeline
    from tools.build_pseudobulk import _get_sample_column

    adata = sc.read_h5ad(str(data_path))
    ensure_pipeline(adata, "mouse")

    profile = adata.uns.get("dataset_profile") or {}
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    age_col = profile.get("age_column") or "age"
    sample_col = _get_sample_column(adata, profile.get("sample_column") or "sample_id")

    if not cell_type:
        counts = adata.obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
        mice_ge = (counts >= MIN_CELLS_PER_SAMPLE).sum(axis=1)
        cell_type = mice_ge.sort_values(ascending=False).index[0]

    sub = adata[adata.obs[ct_col].astype(str) == str(cell_type)].copy()
    mice = _usable_mice(sub, ct_col, sample_col, cell_type)
    if len(mice) < 4:
        raise ValueError(
            f"Need >=4 mice with >={MIN_CELLS_PER_SAMPLE} cells; "
            f"{cell_type} has {len(mice)}."
        )

    mouse_age = {
        m: str(sub.obs.loc[sub.obs[sample_col].astype(str) == m, age_col].iloc[0])
        for m in mice
    }
    mouse_sex = {m: _mouse_sex(m) for m in mice}

    stratum_label = "random split"
    pool = list(mice)

    if mode == "homogeneous":
        strata: dict[tuple[str, str], list[str]] = defaultdict(list)
        for m in mice:
            strata[(mouse_age[m], mouse_sex[m])].append(m)
        homogeneous = sorted(
            [ms for ms in strata.values() if len(ms) >= 4],
            key=len,
            reverse=True,
        )
        if homogeneous:
            pool = list(homogeneous[0])
            stratum_label = f"{mouse_age[pool[0]]} / sex {mouse_sex[pool[0]]}"
        else:
            by_age: dict[str, list[str]] = defaultdict(list)
            for m in mice:
                by_age[mouse_age[m]].append(m)
            age_pools = sorted(
                [ms for ms in by_age.values() if len(ms) >= 4],
                key=len,
                reverse=True,
            )
            if not age_pools:
                raise ValueError(
                    f"No same-age stratum with >=4 mice for {cell_type}. "
                    f"Strata: {{k: len(v) for k, v in strata.items()}}"
                )
            pool = list(age_pools[0])
            stratum_label = f"{mouse_age[pool[0]]} / mixed sex"

    rng = np.random.default_rng(seed)
    perm = list(rng.permutation(pool))
    half = len(perm) // 2
    grp_young = set(perm[:half])
    grp_old = set(perm[half:2 * half])

    sub = sub[sub.obs[sample_col].astype(str).isin(grp_young | grp_old)].copy()
    fake_age = np.where(
        sub.obs[sample_col].astype(str).isin(list(grp_young)),
        FAKE_YOUNG,
        FAKE_OLD,
    )
    sub.obs[age_col] = fake_age
    sub.uns.pop("dataset_profile", None)

    meta = {
        "cell_type": str(cell_type),
        "mode": mode,
        "stratum": stratum_label,
        "fake_young_mice": sorted(grp_young),
        "fake_old_mice": sorted(grp_old),
        "n_mice": len(grp_young | grp_old),
        "n_cells": int(sub.n_obs),
    }
    return sub, meta
