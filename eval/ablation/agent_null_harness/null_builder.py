"""
Construct null datasets for agent-level evaluation.

Whole biological samples are randomly assigned to explicit fake groups within
one cell type. Real donor metadata are preserved for balance auditing.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np

MIN_CELLS_PER_SAMPLE = 20
NULL_GROUP_COLUMN = "null_group"
FAKE_YOUNG = "fake_A"
FAKE_OLD = "fake_B"


def _mouse_sex(mouse_id: str) -> str:
    suffix = str(mouse_id).rsplit("_", 1)[-1].upper()
    return suffix if suffix in ("M", "F") else "?"


def _canonical_allocation(group_a, group_b) -> str:
    """Orientation-invariant ID: A/B and B/A are the same null partition."""
    a = "|".join(sorted(group_a))
    b = "|".join(sorted(group_b))
    return "::".join(sorted((a, b)))


def _stratified_split(mice, strata_by_mouse, rng):
    """Balanced split within strata, with equal final group sizes.

    Each stratum differs by at most one donor between groups. If the total donor
    count is odd, one randomly selected donor from an odd stratum is excluded so
    the fake groups remain the same size.
    """
    strata = defaultdict(list)
    for mouse in mice:
        strata[strata_by_mouse[mouse]].append(mouse)

    group_a, group_b, odd_leftovers = set(), set(), []
    stratum_counts = {}
    for key in sorted(strata, key=str):
        perm = list(rng.permutation(strata[key]))
        paired = len(perm) - (len(perm) % 2)
        half = paired // 2
        left, right = perm[:half], perm[half:paired]
        if bool(rng.integers(0, 2)):
            left, right = right, left
        group_a.update(left)
        group_b.update(right)
        if len(perm) % 2:
            odd_leftovers.append((key, perm[-1]))
        stratum_counts[str(key)] = {"eligible": len(perm), "fake_young": half, "fake_old": half}

    excluded = []
    if len(odd_leftovers) % 2:
        drop_i = int(rng.integers(0, len(odd_leftovers)))
        key, mouse = odd_leftovers.pop(drop_i)
        excluded.append(mouse)
        stratum_counts[str(key)]["excluded"] = 1

    if odd_leftovers:
        order = rng.permutation(len(odd_leftovers))
        odd_leftovers = [odd_leftovers[int(i)] for i in order]
    for i, (key, mouse) in enumerate(odd_leftovers):
        target = group_a if i % 2 == 0 else group_b
        label = "fake_young" if i % 2 == 0 else "fake_old"
        target.add(mouse)
        stratum_counts[str(key)][label] += 1

    if len(group_a) != len(group_b):
        raise RuntimeError("Stratified allocator produced unequal fake groups")
    return group_a, group_b, excluded, stratum_counts


def _balance_table(group_a, group_b, mouse_age, mouse_sex):
    table = {}
    for covariate, values in (("age", mouse_age), ("sex", mouse_sex)):
        levels = sorted(set(values.values()))
        table[covariate] = {
            level: {
                "fake_young": sum(values[m] == level for m in group_a),
                "fake_old": sum(values[m] == level for m in group_b),
            }
            for level in levels
        }
    return table


def _covariate_audit(sub, sample_col, group_col, covariate="null_batch"):
    """Donor-level cross-tab and association strength saved with each allocation."""
    if covariate not in sub.obs.columns:
        return None
    donor = sub.obs[[sample_col, group_col, covariate]].astype(str).drop_duplicates()
    counts = donor.groupby([covariate, group_col]).size()
    table = {}
    for (level, group), n in counts.items():
        table.setdefault(str(level), {})[str(group)] = int(n)
    n = int(len(donor))
    purity = sum(max(level.values()) for level in table.values()) / n if n else None
    return {
        "covariate": covariate,
        "table": table,
        "n_samples": n,
        "purity": round(float(purity), 4) if purity is not None else None,
        "perfect_separation": len(table) > 1 and all(len(level) == 1 for level in table.values()),
    }


def _usable_mice(sub, ct_col: str, sample_col: str, cell_type: str) -> list[str]:
    # Donor enumeration needs metadata only. Slicing AnnData here also slices
    # its large `.raw` sparse matrix and caused cumulative Liver-worker OOMs.
    mask = sub.obs[ct_col].astype(str) == str(cell_type)
    vc = sub.obs.loc[mask, sample_col].astype(str).value_counts()
    return sorted(vc[vc >= MIN_CELLS_PER_SAMPLE].index.tolist())


def _detach_redundant_raw(adata) -> None:
    """Drop harness-only duplicate raw storage after counts are locked."""
    if "counts" not in adata.layers:
        raise RuntimeError("Cannot detach .raw before verified counts are locked")
    adata.raw = None
    adata.uns["_null_source_raw_detached"] = True


def prepare_null_source(data_path: Path, cell_type: str | None = None):
    """Load once and optionally materialize one reusable cell-type subset."""
    import gc
    import scanpy as sc
    from agent.pipeline import ensure_pipeline

    adata = sc.read_h5ad(str(data_path))
    ensure_pipeline(adata, "mouse")
    if cell_type:
        profile = adata.uns.get("dataset_profile") or {}
        ct_col = profile.get("cell_type_column") or "cell_ontology_class"
        subset = adata[adata.obs[ct_col].astype(str) == str(cell_type)].copy()
        # ensure_pipeline has already locked verified raw counts into the counts
        # layer. Keeping `.raw` as well makes every donor-allocation slice copy
        # the same sparse count matrix a second time and exhausts Liver workers.
        # X remains the author-normalized visualization matrix; counts remains
        # the sole DESeq2 input; completed pipeline_state prevents reprocessing.
        _detach_redundant_raw(subset)
        subset.uns["_null_source_cell_type"] = str(cell_type)
        del adata
        gc.collect()
        return subset
    return adata


def build_null_adata(
    data_path: Path,
    cell_type: str,
    seed: int,
    *,
    mode: str = "homogeneous",
    design: str = "valid",
    source_adata=None,
):
    """
    Build a one-cell-type AnnData object with fake_A/fake_B donor labels.

    Parameters
    ----------
    mode:
        ``homogeneous`` â€” split mice from the largest same-age-and-sex stratum
        (paired-transcripts style; removes real age/sex signal).
        ``random`` â€” split all usable mice at random (null-harness style).
        ``stratified`` â€” use all possible mice while balancing real age and sex.
    """
    from tools.build_pseudobulk import _get_sample_column

    adata = source_adata if source_adata is not None else prepare_null_source(data_path)

    profile = adata.uns.get("dataset_profile") or {}
    ct_col = profile.get("cell_type_column") or "cell_ontology_class"
    age_col = profile.get("age_column") or "age"
    sample_col = _get_sample_column(adata, profile.get("sample_column") or "sample_id")

    if not cell_type:
        counts = adata.obs.groupby([ct_col, sample_col], observed=True).size().unstack(fill_value=0)
        mice_ge = (counts >= MIN_CELLS_PER_SAMPLE).sum(axis=1)
        cell_type = mice_ge.sort_values(ascending=False).index[0]

    if adata.uns.get("_null_source_cell_type") == str(cell_type):
        # The worker already owns an immutable materialized cell-type subset.
        # A donor-specific copy is made below after allocation.
        sub = adata
    else:
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
    excluded_mice = []
    stratum_counts = None
    if mode == "stratified":
        strata_by_mouse = {m: (mouse_age[m], mouse_sex[m]) for m in mice}
        grp_young, grp_old, excluded_mice, stratum_counts = _stratified_split(
            mice, strata_by_mouse, rng
        )
        stratum_label = "stratified by real age and sex"
    elif mode in ("homogeneous", "random"):
        perm = list(rng.permutation(pool))
        half = len(perm) // 2
        grp_young = set(perm[:half])
        grp_old = set(perm[half:2 * half])
        excluded_mice = sorted(set(pool) - grp_young - grp_old)
    else:
        raise ValueError(f"Unknown null mode: {mode}")

    sub = sub[sub.obs[sample_col].astype(str).isin(grp_young | grp_old)].copy()
    fake_age = np.where(
        sub.obs[sample_col].astype(str).isin(list(grp_young)),
        FAKE_YOUNG,
        FAKE_OLD,
    )
    # Preserve real age. The agent and DESeq2 compare this dedicated null factor.
    sub.obs[NULL_GROUP_COLUMN] = fake_age
    design_details = {}
    if design == "one_sample_per_group":
        sub.obs[sample_col] = np.where(fake_age == FAKE_YOUNG, "young_sample", "old_sample")
    elif design == "per_cell_sample":
        sub.obs[sample_col] = [f"cell_{i}" for i in range(sub.n_obs)]
    elif design == "confounded":
        # Perfect confound (easy recall case): a batch covariate aligned 1:1 with
        # the fake group -> perfectly separates the two groups -> gate MUST block.
        # Uses DISTINCT labels (batch_X/batch_Y) so it does not collide with the
        # null_group values and derail the agent's contrast routing.
        sub.obs["null_batch"] = np.where(fake_age == FAKE_YOUNG, "batch_X", "batch_Y")
    elif design == "confounded_partial":
        # Harder confound: aligned with the fake groups for all but one donor, so
        # separation is IMPERFECT. The perfect-separation gate is expected NOT to
        # block this -> probes the detection boundary (a partial confound the
        # current gate misses is an honest, reportable limitation).
        mice_arr = sub.obs[sample_col].astype(str).values
        flip = sorted(grp_young)[0]
        design_details["flipped_donor"] = flip
        batch = np.where(fake_age == FAKE_YOUNG, "batch_X", "batch_Y")
        sub.obs["null_batch"] = np.where(mice_arr == flip, "batch_Y", batch)
    elif design == "covariate_balanced":
        # Specificity control (must NOT block): a covariate that is PRESENT but
        # balanced across the fake groups (each level appears in both). A gate
        # that blocks this is over-refusing.
        cov_rng = np.random.default_rng(seed + 7919)
        batch_map = {}
        for grp in (grp_young, grp_old):
            perm = list(cov_rng.permutation(sorted(grp)))
            for i, m in enumerate(perm):
                batch_map[m] = "batch1" if i < len(perm) // 2 else "batch2"
        mice_arr = sub.obs[sample_col].astype(str).values
        sub.obs["null_batch"] = [batch_map.get(m, "batch1") for m in mice_arr]
    elif design in ("contrast_alias", "contrast_alias_with_batch"):
        # Exact second encoding of the biological axis under test. Registration
        # occurs after ensure_pipeline builds the profile in run_sweep.
        sub.obs["null_group_alias"] = np.where(
            fake_age == FAKE_YOUNG, "alias_A", "alias_B"
        )
        design_details["registered_alias"] = "null_group_alias"
        if design == "contrast_alias_with_batch":
            # A registered on-axis alias must not hide an independent off-axis
            # nuisance factor that also perfectly separates the contrast.
            sub.obs["null_batch"] = np.where(
                fake_age == FAKE_YOUNG, "batch_X", "batch_Y"
            )
    elif design != "valid":
        raise ValueError(f"Unknown null design: {design}")
    sub.uns.pop("dataset_profile", None)
    sub.uns.pop("_null_source_cell_type", None)

    meta = {
        "cell_type": str(cell_type),
        "mode": mode,
        "design": design,
        "stratum": stratum_label,
        "null_group_column": NULL_GROUP_COLUMN,
        "null_groups": [FAKE_YOUNG, FAKE_OLD],
        "real_age_column": age_col,
        "fake_young_mice": sorted(grp_young),
        "fake_old_mice": sorted(grp_old),
        "n_mice": len(grp_young | grp_old),
        "n_cells": int(sub.n_obs),
        "excluded_mice": sorted(excluded_mice),
        "stratum_counts": stratum_counts,
        "balance": _balance_table(grp_young, grp_old, mouse_age, mouse_sex),
        "allocation_id": _canonical_allocation(grp_young, grp_old),
        "design_details": design_details,
        "confound_audit": _covariate_audit(
            sub, sample_col, NULL_GROUP_COLUMN
        ),
    }
    return sub, meta
