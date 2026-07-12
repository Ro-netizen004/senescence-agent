"""Column-role schema for the GUI confirm-panel.

Surfaces the auto-detected dataset profile as an editable set of column roles
(cell type / sample / grouping variable / ignore) and applies user overrides
back onto the profile. Because every tool and the admissibility gate read the
profile through ``resolve_contrast``, a user's override here flows to all of
them automatically — the profile is the single source of truth.
"""

from __future__ import annotations

from typing import Any

_MISSING = ("", "nan", "none", "na", "unknown", "<na>")


def _role_for(col: str, prof: dict) -> str:
    if col == prof.get("cell_type_column"):
        return "cell_type"
    if col == prof.get("sample_column"):
        return "sample"
    if col in [g.get("column") for g in (prof.get("group_columns") or [])]:
        return "group"
    return "ignore"


def _samples_per_value(obs, sample_col, group_col) -> dict:
    """{group value: number of distinct samples} — reveals which groupings are
    actually testable (need >=2 samples per group). Missing/NaN values (e.g.
    values excluded from a custom grouping) are dropped, not shown as a group."""
    if not sample_col or sample_col not in obs.columns or group_col not in obs.columns:
        return {}
    sl = obs[[sample_col, group_col]].astype(str).drop_duplicates()
    counts = sl.groupby(group_col)[sample_col].nunique()
    return {
        str(k): int(v) for k, v in counts.items()
        if str(k).strip().lower() not in _MISSING
    }


def build_column_roles(adata) -> dict:
    """Return the per-column role table + current assignments + dropdown options."""
    prof = adata.uns.get("dataset_profile") or {}
    obs = adata.obs
    group_names = [g.get("column") for g in (prof.get("group_columns") or [])]
    sample_col = prof.get("sample_column")

    columns = []
    for c in obs.columns:
        raw = obs[c].astype(str).unique().tolist()
        # Drop missing/NaN so an excluded/unmapped value never shows as a group.
        vals = [v for v in raw if v.strip().lower() not in _MISSING]
        entry = {
            "name": str(c),
            "role": _role_for(c, prof),
            "n_levels": len(vals),
            "values": sorted(vals)[:12],
        }
        if str(c) in group_names:
            entry["samples_per_value"] = _samples_per_value(obs, sample_col, str(c))
        columns.append(entry)

    return {
        "columns": columns,
        "cell_type_column": prof.get("cell_type_column"),
        "sample_column": prof.get("sample_column"),
        "primary_group_column": prof.get("primary_group_column"),
        # Options for the two dropdowns the MVP panel exposes.
        "group_options": group_names,
        "sample_options": [str(c) for c in obs.columns],
        "n_cells": int(adata.n_obs),
    }


def apply_column_overrides(adata, overrides: dict[str, Any]) -> dict:
    """Validate and apply user role overrides onto the cached dataset profile.

    Returns {ok, errors, warnings, profile}. On any hard error nothing is
    changed. Non-fatal concerns (e.g. a sample column that looks per-cell) are
    surfaced as warnings; the downstream admissibility gate still has final say.
    """
    prof = dict(adata.uns.get("dataset_profile") or {})
    obs = adata.obs
    errors: list[str] = []
    warnings: list[str] = []

    def _exists(col):
        return col in obs.columns

    sample_col = overrides.get("sample_column")
    if sample_col:
        if not _exists(sample_col):
            errors.append(f"Sample column '{sample_col}' not found in the dataset.")
        else:
            prof["sample_column"] = sample_col
            if obs[sample_col].astype(str).nunique() >= adata.n_obs * 0.9:
                warnings.append(
                    f"'{sample_col}' has about one value per cell — that's a cell "
                    f"identifier, not a biological replicate unit. Statistical tests "
                    f"will be blocked as pseudoreplication."
                )

    group_col = overrides.get("primary_group_column")
    if group_col:
        if not _exists(group_col):
            errors.append(f"Grouping column '{group_col}' not found in the dataset.")
        else:
            vals = [v for v in obs[group_col].astype(str).unique().tolist()
                    if v.strip().lower() not in _MISSING]
            if len(vals) < 2:
                errors.append(f"Grouping column '{group_col}' has fewer than 2 groups.")
            else:
                prof["primary_group_column"] = group_col
                names = [g.get("column") for g in (prof.get("group_columns") or [])]
                if group_col not in names:
                    prof.setdefault("group_columns", []).append({
                        "column": group_col,
                        "values": sorted(vals)[:20],
                        "n_levels": len(vals),
                    })
                if len(vals) > 12:
                    warnings.append(
                        f"'{group_col}' has {len(vals)} levels — looks continuous. "
                        f"Contrasts compare exactly two of its values."
                    )

    cell_type_col = overrides.get("cell_type_column")
    if cell_type_col:
        if not _exists(cell_type_col):
            errors.append(f"Cell-type column '{cell_type_col}' not found in the dataset.")
        else:
            prof["cell_type_column"] = cell_type_col

    # Custom grouping: bucket raw values of a source column into named groups
    # (e.g. {control: [CTRL_2, ETO_day_0], senescent: [ETO_1, ETO_2, ETO_day_10]}).
    # Materialised as a derived obs column that becomes the primary grouping.
    grouping = overrides.get("grouping")
    if grouping and grouping.get("groups"):
        source = grouping.get("column")
        buckets = {k: list(v) for k, v in grouping["groups"].items() if v}
        if not source or not _exists(source):
            errors.append(f"Grouping source column '{source}' not found.")
        elif len(buckets) < 2:
            errors.append("Define at least two non-empty comparison groups.")
        else:
            val2label: dict[str, str] = {}
            for label, vals in buckets.items():
                for v in vals:
                    val2label[str(v)] = label
            derived = "comparison_group"
            adata.obs[derived] = (
                obs[source].astype(str).map(val2label).astype("object")
            )
            # Preserve the user's group order: first group is the reference/baseline,
            # so a positive log2 fold-change means higher in the second group.
            labels = list(buckets.keys())
            prof["primary_group_column"] = derived
            prof["group_columns"] = [
                g for g in (prof.get("group_columns") or []) if g.get("column") != derived
            ] + [{"column": derived, "values": labels, "n_levels": len(labels)}]
            spv = _samples_per_value(obs, prof.get("sample_column"), derived)
            if sum(1 for n in spv.values() if n >= 2) < 2:
                warnings.append(
                    f"Custom groups are not both replicated ({spv}). A statistical "
                    f"test will be blocked; results would be descriptive only."
                )

    if not errors:
        adata.uns["dataset_profile"] = prof

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "profile": {
            "cell_type_column": prof.get("cell_type_column"),
            "sample_column": prof.get("sample_column"),
            "primary_group_column": prof.get("primary_group_column"),
        },
    }
