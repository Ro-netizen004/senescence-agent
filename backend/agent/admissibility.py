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

# Minimum biological replicates per group for any variance estimate to exist.
MIN_ADMISSIBLE_REPLICATES = 2
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

# Age / condition encodings. A second grouping-like column that separates the
# contrast IS the biology under test, not a confounder — so it is excluded.
_GROUPING_LIKE_COLS = frozenset({
    "age", "age_group", "development_stage", "timepoint", "time_point",
    "donor_age", "condition", "label_group", "published_senescent",
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
    """One row per sample: its group value (and any extra covariates)."""
    cols = [sample_col, group_col] + [c for c in (extra_cols or []) if c in adata.obs.columns]
    df = adata.obs[cols].astype(str).drop_duplicates(subset=[sample_col])
    return df


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
        if str(c).lower() in _NON_COVARIATE_COLS or str(c).lower() in _GROUPING_LIKE_COLS:
            continue
        try:
            sl = obs[[sample_col, c]].astype(str).drop_duplicates(subset=[sample_col])
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
        if sub.empty:
            continue
        # For each covariate value, how many of the two groups does it appear in?
        by_val = sub.groupby(c)[group_col].nunique()
        # >1 distinct value AND every value confined to a single group → perfect separation.
        if len(by_val) > 1 and (by_val == 1).all():
            hits.append(c)
    return hits


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

        low = [g for g, n in reps.items() if n < MIN_ADMISSIBLE_REPLICATES]
        if low:
            excl_note = ""
            if excluded:
                excl_note = (
                    f" Samples with < {MIN_CELLS_PER_SAMPLE} cells of this cell type were "
                    f"excluded as unreliable pseudobulk replicates (excluded per group: "
                    f"{excluded}); too few cells give a library-size-skewed profile that "
                    f"produces spurious fold-changes."
                )
            reasons.append(
                f"insufficient_replicates: groups {low} have < {MIN_ADMISSIBLE_REPLICATES} "
                f"biological replicates with >= {MIN_CELLS_PER_SAMPLE} cells (usable "
                f"counts={reps}). No between-replicate variance can be estimated; a per-cell "
                f"test here would be pseudoreplication.{excl_note}"
            )

        few = [g for g, n in reps.items() if MIN_ADMISSIBLE_REPLICATES <= n < RECOMMENDED_REPLICATES]
        if few:
            warnings.append(
                f"few_replicates: groups {few} have < {RECOMMENDED_REPLICATES} replicates "
                f"(counts={reps}); the inference is admissible but low-powered."
            )

        confounders = _confounded_with(scoped, sample_col, group_col, groups)
        if confounders:
            checks["confounded_with"] = confounders
            reasons.append(
                f"confounded_contrast: the {ref} vs {comp} contrast is perfectly separated "
                f"by {confounders} at the sample level; any difference cannot be attributed "
                f"to {group_col} rather than {confounders}. Choose a contrast where {confounders} "
                f"vary within each group, or balance the design."
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
