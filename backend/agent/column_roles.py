"""Column-role schema for the GUI confirm-panel.

Surfaces the auto-detected dataset profile as an editable set of column roles
(cell type / sample / grouping variable / ignore) and applies user overrides
back onto the profile. Because every tool and the admissibility gate read the
profile through ``resolve_contrast``, a user's override here flows to all of
them automatically — the profile is the single source of truth.
"""

from __future__ import annotations

from typing import Any

from agent.admissibility import MIN_DESEQ2_REPLICATES

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


def _is_exact_sample_reencoding(obs, sample_col, left, right) -> bool:
    """True when two donor-level columns deterministically encode each other."""
    if not sample_col or any(c not in obs.columns for c in (sample_col, left, right)):
        return False
    frame = obs[[sample_col, left, right]].drop_duplicates()
    if frame[[left, right]].isna().any().any():
        return False
    if frame.groupby(sample_col, observed=True)[[left, right]].nunique().max().max() > 1:
        return False
    frame = frame.drop_duplicates(subset=[sample_col])
    return (
        frame.groupby(left, observed=True)[right].nunique().max() == 1
        and frame.groupby(right, observed=True)[left].nunique().max() == 1
    )


def build_column_roles(adata) -> dict:
    """Return the per-column role table + current assignments + dropdown options."""
    prof = adata.uns.get("dataset_profile") or {}
    obs = adata.obs
    group_names = [g.get("column") for g in (prof.get("group_columns") or [])]
    sample_col = prof.get("sample_column")

    # Covariates must be sample-level: every biological sample has exactly
    # one value. Exclude identity and outcome columns from the selector.
    excluded = {
        sample_col, prof.get("cell_type_column"),
        prof.get("primary_group_column"), "comparison_group",
    }
    primary_provenance = (
        (prof.get("derived_columns") or {}).get(prof.get("primary_group_column")) or {}
    )
    if primary_provenance.get("source"):
        excluded.add(str(primary_provenance["source"]))
    covariate_options = []
    if sample_col and sample_col in obs.columns:
        n_samples = obs[sample_col].astype(str).nunique()
        for c in obs.columns:
            if c in excluded:
                continue
            levels_per_sample = obs.groupby(sample_col, observed=True)[c].nunique(dropna=False)
            n_levels = obs[c].nunique(dropna=False)
            if (not levels_per_sample.empty and levels_per_sample.max() == 1
                    and 1 < n_levels < n_samples):
                covariate_options.append(str(c))

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
        "covariate_options": covariate_options,
        "deseq2_covariates": list(prof.get("deseq2_covariates") or []),
        "contrast_aliases": dict(prof.get("contrast_aliases") or {}),
        "derived_columns": dict(prof.get("derived_columns") or {}),
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

    if "deseq2_covariates" in overrides:
        covariates = list(dict.fromkeys(overrides.get("deseq2_covariates") or []))
        effective_sample = sample_col or prof.get("sample_column")
        effective_group = (
            "comparison_group" if overrides.get("grouping")
            else group_col or prof.get("primary_group_column")
        )
        grouping_source = (overrides.get("grouping") or {}).get("column")
        for covariate in covariates:
            if not _exists(covariate):
                errors.append(f"Covariate '{covariate}' not found in the dataset.")
                continue
            effective_cell_type = overrides.get("cell_type_column") or prof.get("cell_type_column")
            if covariate in {
                effective_sample, effective_group, effective_cell_type, grouping_source,
            }:
                errors.append(
                    f"'{covariate}' cannot be both a DESeq2 covariate and a "
                    "sample/group/group-source/cell-type column."
                )
                continue
            if not effective_sample or effective_sample not in obs.columns:
                errors.append("A biological sample column is required before selecting DESeq2 covariates.")
                break
            per_sample = obs.groupby(effective_sample, observed=True)[covariate].nunique(dropna=False)
            if not per_sample.empty and per_sample.max() > 1:
                errors.append(f"Covariate '{covariate}' varies within biological samples.")
        if not errors:
            prof["deseq2_covariates"] = covariates

    if overrides.get("contrast_aliases") is not None:
        requested_aliases = overrides.get("contrast_aliases") or {}
        validated_aliases = {}
        effective_sample = sample_col or prof.get("sample_column")
        for axis, aliases in requested_aliases.items():
            if not _exists(axis):
                errors.append(f"Contrast alias axis '{axis}' not found in the dataset.")
                continue
            valid = []
            for alias in dict.fromkeys(aliases or []):
                if alias == axis:
                    continue
                if not _exists(alias):
                    errors.append(f"Contrast alias column '{alias}' not found in the dataset.")
                elif not _is_exact_sample_reencoding(obs, effective_sample, axis, alias):
                    errors.append(
                        f"'{alias}' is not an exact donor-level re-encoding of '{axis}'."
                    )
                else:
                    valid.append(alias)
            if valid:
                validated_aliases[str(axis)] = valid
        if not errors:
            prof["contrast_aliases"] = validated_aliases

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
            prof.setdefault("derived_columns", {})[derived] = {
                "source": str(source),
                "kind": "value_mapping",
                "mapping": dict(val2label),
            }
            prof["group_columns"] = [
                g for g in (prof.get("group_columns") or []) if g.get("column") != derived
            ] + [{"column": derived, "values": labels, "n_levels": len(labels)}]
            spv = _samples_per_value(obs, prof.get("sample_column"), derived)
            if sum(1 for n in spv.values() if n >= MIN_DESEQ2_REPLICATES) < 2:
                warnings.append(
                    f"Custom groups do not both have at least "
                    f"{MIN_DESEQ2_REPLICATES} biological samples ({spv}). "
                    f"DESeq2 will be blocked; descriptive analysis remains available."
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
            "deseq2_covariates": list(prof.get("deseq2_covariates") or []),
            "contrast_aliases": dict(prof.get("contrast_aliases") or {}),
            "derived_columns": dict(prof.get("derived_columns") or {}),
        },
    }
