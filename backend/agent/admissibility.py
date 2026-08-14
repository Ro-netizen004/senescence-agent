"""
Admissibility pre-check (Gate 1 of 2).

Runs BEFORE an inferential tool executes. Answers: given the data's *design*,
is this inference even valid to attempt? Blocks inadmissible inferences up front
(pseudoreplication, insufficient replicates, confounded contrast, circular
inference) so an invalid claim can never be computed in the first place.

This is deterministic and LLM-free by design — the LLM may propose an intent,
but it cannot make an inadmissible inference admissible.

Companion to the justification post-check in inference_state.build_state_record.
"""

from __future__ import annotations

from typing import Optional

# Score tests can run cautiously with two replicates per group. DESeq2 needs
# at least three because its dispersion prior is poorly estimated below that.
MIN_ADMISSIBLE_REPLICATES = 2
MIN_DESEQ2_REPLICATES = 3
RECOMMENDED_REPLICATES = 3

# Group-comparison tools that require biological replicates to be admissible.
_REPLICATE_INFERENCE_TOOLS = ("test_senescence_difference", "run_deseq2")

# Per-cell cluster-marker DE: groups are defined on the same expression later
# tested — circular / double-dipping. Admissible only as descriptive discovery.
_CIRCULAR_TOOLS = ("differential_expression",)

# Columns that are never sample-level technical/biological covariates: cell
# identifiers, expression-derived labels, continuous QC metrics, and analysis
# outputs. These are excluded from the generic confounder scan.
_NON_COVARIATE_COLS = frozenset({
    "cell", "cell_id", "barcode", "index",
    "cell_ontology_class", "cell_ontology_id", "cell_type", "celltype",
    "free_annotation", "predicted_cell_type",
    "leiden", "louvain", "clusters",
    "n_genes", "n_counts", "n_genes_by_counts", "total_counts", "pct_counts_mt",
    "senescence_score",
    "tissue",
})

# Above this many distinct sample-level values a column is treated as
# high-cardinality / continuous and skipped by the confounder scan.
_MAX_COVARIATE_CARDINALITY = 10


def _missing_like(value: str) -> bool:
    return str(value).strip().lower() in ("", "nan", "none", "na", "unknown", "<na>")


def _profile(adata) -> dict:
    return adata.uns.get("dataset_profile") or {}


def _resolve_sample_column(adata) -> Optional[str]:
    try:
        from tools.build_pseudobulk import _get_sample_column
        return _get_sample_column(adata, (_profile(adata)).get("sample_column") or "sample_id")
    except Exception:
        return None


def _sample_level_frame(adata, sample_col, group_col, extra_cols=None):
    """One row per sample, retaining only values constant within that sample."""
    cols = [sample_col, group_col] + [c for c in (extra_cols or []) if c in adata.obs.columns]
    obs = adata.obs[cols].astype(str)
    rows = []
    for sample, frame in obs.groupby(sample_col, sort=False):
        row = {sample_col: sample}
        for c in cols[1:]:
            values = [v for v in frame[c].unique().tolist() if not _missing_like(v)]
            row[c] = values[0] if len(values) == 1 else None
        rows.append(row)
    import pandas as pd
    return pd.DataFrame(rows, columns=cols)


def _inconsistent_sample_columns(adata, sample_col, columns) -> dict[str, list[str]]:
    """Columns with more than one non-missing value inside a biological sample."""
    inconsistent = {}
    obs = adata.obs
    for c in columns:
        if c not in obs.columns:
            continue
        bad = []
        for sample, values in obs[[sample_col, c]].astype(str).groupby(sample_col)[c]:
            observed = {v for v in values if not _missing_like(v)}
            if len(observed) > 1:
                bad.append(str(sample))
        if bad:
            inconsistent[str(c)] = sorted(bad)
    return inconsistent


def _replicates_per_group(adata, sample_col, group_col, groups, min_cells=1):
    """Count biological replicates per group, keeping only samples with at least
    ``min_cells`` cells of the (already cell-type-scoped) population. A sample of
    a handful of cells is not a reliable pseudobulk replicate, so it does not
    count toward the replicate total — matching the null harness, which gates on
    the identical MIN_CELLS_PER_SAMPLE threshold.

    Returns ``(usable_counts, excluded_counts)``: usable = samples with
    >= ``min_cells`` cells; excluded = samples dropped for being below it.
    """
    obs = adata.obs[[sample_col, group_col]].astype(str)
    counts, excluded = {}, {}
    for g in groups:
        gs = str(g)
        per_sample = obs.loc[obs[group_col] == gs, sample_col].value_counts()
        usable = int((per_sample >= min_cells).sum())
        dropped = int((per_sample < min_cells).sum())
        counts[gs] = usable
        if dropped:
            excluded[gs] = dropped
    return counts, excluded


def _candidate_covariate_columns(adata, sample_col, group_col) -> list[str]:
    """Sample-level covariates worth checking for confounding: categorical-ish
    columns that vary across samples but aren't identifiers, grouping encodings,
    expression-derived labels, or continuous QC metrics."""
    obs = adata.obs
    try:
        n_samples = obs[sample_col].astype(str).nunique()
    except Exception:
        n_samples = 0

    candidates = []
    for c in obs.columns:
        if c == sample_col or c == group_col:
            continue
        if str(c).lower() in _NON_COVARIATE_COLS:
            continue
        try:
            if _inconsistent_sample_columns(adata, sample_col, [c]):
                continue
            sl = _sample_level_frame(adata, sample_col, group_col, [c])
            card = sl[c].map(lambda v: None if _missing_like(v) else v).nunique(dropna=True)
        except Exception:
            continue
        if card <= 1:                                  # constant → cannot separate
            continue
        if n_samples and card >= n_samples:            # per-sample identifier, not a covariate
            continue
        if card > _MAX_COVARIATE_CARDINALITY:          # high-cardinality / continuous
            continue
        candidates.append(c)
    return candidates


def _confounded_with(adata, sample_col, group_col, groups) -> list[str]:
    """
    Return covariate columns that PERFECTLY separate the two contrast groups at
    the sample level (every non-missing value of the covariate occurs in only
    one group). Scans covariates generically rather than from a fixed allowlist,
    so an unforeseen confounding column is still caught.
    """
    group_strs = [str(g) for g in groups]
    candidates = _candidate_covariate_columns(adata, sample_col, group_col)
    if not candidates:
        return []

    df = _sample_level_frame(adata, sample_col, group_col, candidates)
    df = df[df[group_col].isin(group_strs)]

    hits = []
    for c in candidates:
        sub = df[[group_col, c]]
        sub = sub[~sub[c].map(_missing_like)]
        if sub.empty or set(sub[group_col].unique()) != set(group_strs):
            continue
        # For each covariate value, how many of the two groups does it appear in?
        by_val = sub.groupby(c)[group_col].nunique()
        # >1 distinct value AND every value confined to a single group → perfect separation.
        if len(by_val) > 1 and (by_val == 1).all():
            hits.append(c)
    return hits


def _confounding_associations(adata, sample_col, group_col, groups) -> dict[str, dict]:
    """Return auditable sample-level association scores for covariates."""
    group_strs = [str(g) for g in groups]
    candidates = _candidate_covariate_columns(adata, sample_col, group_col)
    if not candidates:
        return {}
    df = _sample_level_frame(adata, sample_col, group_col, candidates)
    df = df[df[group_col].isin(group_strs)]
    assessments = {}
    for c in candidates:
        sub = df[[group_col, c]]
        sub = sub[~sub[c].map(_missing_like)]
        table = {
            str(level): {
                str(group): int(n)
                for group, n in frame[group_col].value_counts().items()
            }
            for level, frame in sub.groupby(c)
        }
        represented = sorted(sub[group_col].unique().tolist())
        n = len(sub)
        purity = sum(max(level.values()) for level in table.values()) / n if n else None
        assessments[str(c)] = {
            "table": table,
            "n_observed_samples": n,
            "n_missing_samples": int(len(df) - n),
            "represented_groups": represented,
            "purity": round(float(purity), 4) if purity is not None else None,
            "perfect_separation": (
                set(represented) == set(group_strs)
                and len(table) > 1
                and all(len(level) == 1 for level in table.values())
            ),
        }
    return assessments


def _registered_contrast_encodings(adata, group_col: str) -> set[str]:
    """Columns explicitly registered as aliases or sources of this contrast."""
    profile = _profile(adata)
    aliases = profile.get("contrast_aliases") or {}
    registered = set(str(c) for c in aliases.get(group_col, []) or [])
    for axis, columns in aliases.items():
        encoded = [str(c) for c in columns or []]
        if group_col in encoded:
            registered.add(str(axis))
            registered.update(c for c in encoded if c != group_col)
    derived_columns = profile.get("derived_columns") or {}
    provenance = derived_columns.get(group_col) or {}
    if provenance.get("source"):
        registered.add(str(provenance["source"]))
    # Provenance is bidirectional for confound detection. If the active contrast
    # is the source axis (for example age), a dashboard-created column derived
    # from it (comparison_group) is an encoding of that same biological axis,
    # not an independent nuisance variable capable of confounding it.
    for derived, derived_provenance in derived_columns.items():
        if str((derived_provenance or {}).get("source")) == str(group_col):
            registered.add(str(derived))
    return registered


def check_admissibility(tool_name: str, args: dict, adata) -> dict:
    """
    Returns:
      {
        "admissible": bool,
        "blocked_reasons": [...],   # each blocks the inference
        "warnings": [...],          # non-blocking, surfaced to user
        "checks": {...},            # what was inspected (for transparency/paper)
      }
    """
    args = args or {}
    reasons: list[str] = []
    warnings: list[str] = []
    checks: dict = {"tool": tool_name}

    # Resolve the contrast through the SAME resolver the tools use, so the gate
    # validates exactly what will run (no gate/tool drift).
    from agent.contrast import resolve_contrast
    spec = resolve_contrast(adata, args)
    group_col = spec.group_column
    ct_col = spec.cell_type_column

    # ── Circular inference (per-cell cluster-marker DE) ──────────────────
    if tool_name in _CIRCULAR_TOOLS:
        warnings.append(
            "circular_inference: clusters are defined on the same expression being "
            "tested; markers are admissible as descriptive discovery only, not as "
            "inferential differential expression."
        )
        checks["circular_inference"] = True

    # ── Replicate-based group comparisons ────────────────────────────────
    if tool_name in _REPLICATE_INFERENCE_TOOLS:
        sample_col = spec.sample_column
        checks["sample_column"] = sample_col

        if tool_name == "run_deseq2":
            try:
                from tools.build_pseudobulk import _extract_counts_matrix
                _, _, count_check = _extract_counts_matrix(adata)
                checks["count_validation"] = count_check
            except ValueError as exc:
                reasons.append(f"invalid_raw_counts: {exc}")
                return _finish(reasons, warnings, checks)

        if sample_col is None:
            reasons.append(
                "no_replicate_unit: no sample/donor column found, so the statistical "
                "unit is the cell. A between-group test would be pseudoreplication."
            )
            return _finish(reasons, warnings, checks)

        if group_col not in adata.obs.columns:
            reasons.append(f"missing_group_column: '{group_col}' not in dataset.")
            return _finish(reasons, warnings, checks)

        # A requested cell type that isn't in the dataset must be reported plainly,
        # not as a "0 replicates / pseudoreplication" block (which is misleading).
        requested_ct = args.get("cell_type")
        if requested_ct and not spec.cell_type:
            available = (
                sorted(adata.obs[ct_col].astype(str).unique().tolist())
                if ct_col in adata.obs.columns else []
            )
            reasons.append(
                f"cell_type_not_found: '{requested_ct}' is not a cell type in this "
                f"dataset. Available cell types: {available}."
            )
            return _finish(reasons, warnings, checks)

        if not spec.has_groups:
            reasons.append(
                f"groups_not_specified: two groups of '{group_col}' are required. "
                f"Specify reference_group and comparison_group."
            )
            return _finish(reasons, warnings, checks)

        covariates = list(dict.fromkeys(args.get("covariates") or []))
        missing_covariates = [c for c in covariates if c not in adata.obs.columns]
        if missing_covariates:
            reasons.append(f"missing_covariates: columns not found: {missing_covariates}")
            return _finish(reasons, warnings, checks)
        illegal_covariates = [
            c for c in covariates if c in {group_col, sample_col, ct_col}
        ]
        if illegal_covariates:
            reasons.append(
                "invalid_covariates: grouping, sample-ID, and cell-type columns cannot "
                f"be adjustment covariates: {illegal_covariates}"
            )
            return _finish(reasons, warnings, checks)
        checks["requested_covariates"] = covariates

        ref, comp = spec.reference_group, spec.comparison_group
        groups = [ref, comp]
        checks["contrast"] = {"reference": ref, "comparison": comp, "group_column": group_col}

        # Restrict to the requested cell type if the tool uses one
        scoped = adata
        if spec.cell_type and ct_col in adata.obs.columns:
            scoped = adata[adata.obs[ct_col].astype(str) == spec.cell_type]
            checks["cell_type"] = spec.cell_type

        from tools.build_pseudobulk import MIN_CELLS_PER_SAMPLE

        reps, excluded = _replicates_per_group(
            scoped, sample_col, group_col, groups, MIN_CELLS_PER_SAMPLE
        )
        checks["replicates_per_group"] = reps
        checks["min_cells_per_sample"] = MIN_CELLS_PER_SAMPLE
        if excluded:
            checks["samples_excluded_low_cells"] = excluded

        min_replicates = (
            MIN_DESEQ2_REPLICATES if tool_name == "run_deseq2"
            else MIN_ADMISSIBLE_REPLICATES
        )
        checks["minimum_replicates_per_group"] = min_replicates
        low = [g for g, n in reps.items() if n < min_replicates]
        if low:
            excl_note = ""
            if excluded:
                excl_note = (
                    f" Samples with < {MIN_CELLS_PER_SAMPLE} cells of this cell type were "
                    f"excluded as unreliable pseudobulk replicates (excluded per group: "
                    f"{excluded}); too few cells give a library-size-skewed profile that "
                    f"produces spurious fold-changes."
                )
            if tool_name == "run_deseq2":
                rationale = (
                    "DESeq2 dispersion estimation is unreliable with fewer than 3 "
                    "replicates per group, so adjusted-p discoveries would not be trusted."
                )
            else:
                rationale = (
                    "No between-replicate variance can be estimated; a per-cell test "
                    "here would be pseudoreplication."
                )
            reasons.append(
                f"insufficient_replicates: groups {low} have < {min_replicates} "
                f"biological replicates with >= {MIN_CELLS_PER_SAMPLE} cells (usable "
                f"counts={reps}). {rationale}{excl_note}"
            )

        few = [g for g, n in reps.items() if min_replicates <= n < RECOMMENDED_REPLICATES]
        if few:
            warnings.append(
                f"few_replicates: groups {few} have < {RECOMMENDED_REPLICATES} replicates "
                f"(counts={reps}); the inference is admissible but low-powered."
            )

        consistency_columns = [
            c for c in scoped.obs.columns
            if c == group_col or (
                c != sample_col and str(c).lower() not in _NON_COVARIATE_COLS
            )
        ]
        inconsistent = _inconsistent_sample_columns(
            scoped, sample_col, consistency_columns
        )
        if group_col in inconsistent:
            reasons.append(
                f"inconsistent_group_within_sample: '{group_col}' has multiple values "
                f"within biological samples {inconsistent[group_col]}."
            )
        covariate_inconsistent = {k: v for k, v in inconsistent.items() if k != group_col}
        if covariate_inconsistent:
            checks["non_sample_level_columns_skipped"] = covariate_inconsistent

        if group_col not in inconsistent:
            design_meta = _sample_level_frame(
                scoped, sample_col, group_col, covariates
            )
            design_meta = design_meta[
                design_meta[group_col].astype(str).isin([str(g) for g in groups])
            ]
            try:
                from agent.design_validation import validate_factor_design
                checks["design_validation"] = validate_factor_design(
                    design_meta, group_col, covariates
                )
            except ValueError as exc:
                reasons.append(f"invalid_design_matrix: {exc}")

        associations = _confounding_associations(scoped, sample_col, group_col, groups)
        checks["confounding_associations"] = associations
        registered_encodings = _registered_contrast_encodings(scoped, group_col)
        redundant_encodings = [
            c for c, result in associations.items()
            if result["perfect_separation"] and c in registered_encodings
        ]
        if redundant_encodings:
            checks["redundant_contrast_encodings"] = redundant_encodings
            warnings.append(
                "redundant_contrast_encoding: the contrast is also explicitly encoded "
                f"by {redundant_encodings}. These registered aliases/sources were not "
                "treated as nuisance confounders and must not be added as covariates."
            )
        confounders = [
            c for c, result in associations.items()
            if result["perfect_separation"] and c not in registered_encodings
        ]
        if confounders:
            checks["confounded_with"] = confounders
            reasons.append(
                f"confounded_contrast: the {ref} vs {comp} contrast is perfectly separated "
                f"by {confounders} at the sample level; any difference cannot be attributed "
                f"to {group_col} rather than {confounders}. Choose a contrast where {confounders} "
                f"vary within each group, or balance the design."
            )

        baseline_purity = max(reps.values()) / max(1, sum(reps.values()))
        partial = [
            c for c, result in associations.items()
            if not result["perfect_separation"]
            and set(result["represented_groups"]) == set(str(g) for g in groups)
            and result["purity"] is not None
            and result["purity"] > baseline_purity
        ]
        if partial:
            checks["partially_associated_covariates"] = partial
            warnings.append(
                "partial_confounding: sample-level covariates are associated with the "
                f"contrast but do not perfectly separate it: {partial}. Inspect the "
                "reported tables and include scientifically justified covariates in the model."
            )

    return _finish(reasons, warnings, checks)


def _finish(reasons, warnings, checks) -> dict:
    return {
        "admissible": len(reasons) == 0,
        "blocked_reasons": reasons,
        "warnings": warnings,
        "checks": checks,
    }


def admissibility_block_result(tool_name: str, admissibility: dict) -> dict:
    """
    Build a BLOCKED-shaped tool result when a pre-check fails, so the existing
    inference-state machine + renderer refuse it without running the tool.
    """
    return {
        "error": "inadmissible_inference",
        "tool": tool_name,
        "admissibility": admissibility,
        "message": (
            "This inference is inadmissible given the data design and was not run. "
            + " ".join(admissibility.get("blocked_reasons", []))
        ),
    }
