"""Single source of truth for "what is being compared".

Every group-comparison tool (DESeq2, senescence test, age comparison) and the
admissibility gate resolve their contrast through :func:`resolve_contrast`, so
they can never disagree about the cell type, grouping variable, groups, or
replicate unit. The resolver reads the (possibly user-edited) dataset profile
plus the tool's arguments — the profile is authoritative, which is what lets a
user's column-role choices in the GUI flow to every tool automatically.

Kept dependency-light (no scanpy/matplotlib) so routing and the gate can import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# Same order used elsewhere for auto-detecting the biological replicate unit.
_SAMPLE_CANDIDATES = [
    "sample_id", "donor_id", "patient_id", "subject_id",
    "mouse.id", "mouse_id", "donor", "participant_id", "individual", "batch",
]


@dataclass
class ContrastSpec:
    cell_type: Optional[str]           # resolved to an exact dataset value (or None)
    cell_type_column: str
    group_column: str                  # the grouping variable (age/condition/...)
    reference_group: Optional[str]
    comparison_group: Optional[str]
    sample_column: Optional[str]       # biological replicate unit (None if absent)

    @property
    def has_groups(self) -> bool:
        return bool(
            self.reference_group
            and self.comparison_group
            and self.reference_group != self.comparison_group
        )


def _resolve_sample_column(adata, prof: dict, explicit: Optional[str]) -> Optional[str]:
    if explicit and explicit in adata.obs.columns:
        return explicit
    p = prof.get("sample_column")
    if p and p in adata.obs.columns:
        return p
    for c in _SAMPLE_CANDIDATES:
        if c in adata.obs.columns:
            return c
    return None


def resolve_contrast(adata, args: Optional[dict[str, Any]] = None) -> ContrastSpec:
    """Resolve the full contrast from the dataset profile + tool args.

    Precedence for each field: explicit tool arg > dataset profile > fallback.
    ``age_column`` / ``reference_age`` / ``comparison_age`` are accepted as
    deprecated aliases of ``group_column`` / ``reference_group`` /
    ``comparison_group``. For an age grouping with no explicit groups, the
    youngest and oldest ages are filled in (preserves aging-atlas behaviour).
    """
    args = args or {}
    prof = adata.uns.get("dataset_profile") or {}
    obs = adata.obs

    ct_col = (
        args.get("cell_type_column")
        or prof.get("cell_type_column")
        or "cell_ontology_class"
    )
    group_col = (
        args.get("group_column")
        or args.get("age_column")
        or prof.get("primary_group_column")
        or prof.get("age_column")
        or "age"
    )
    sample_col = _resolve_sample_column(adata, prof, args.get("sample_column"))

    # Resolve the requested cell type against the real labels.
    requested_ct = args.get("cell_type")
    cell_type = requested_ct
    if requested_ct and ct_col in obs.columns:
        from tools.text_match import resolve_cell_type
        available = sorted(obs[ct_col].astype(str).unique().tolist())
        cell_type = resolve_cell_type(requested_ct, available)

    ref = args.get("reference_group") or args.get("reference_age")
    comp = args.get("comparison_group") or args.get("comparison_age")

    # Fill in the groups when they're unambiguous:
    if not ref or not comp:
        age_col = prof.get("age_column")
        if group_col == age_col:
            # Age → youngest vs oldest (legacy default).
            ref = ref or prof.get("youngest")
            comp = comp or prof.get("oldest")
        else:
            # Any grouping variable with exactly two levels has only one possible
            # contrast (e.g. control vs senescent) — use it.
            gc = next(
                (g for g in (prof.get("group_columns") or [])
                 if g.get("column") == group_col),
                None,
            )
            values = (gc or {}).get("values") or []
            if len(values) == 2:
                ref = ref or values[0]
                comp = comp or values[1]

    return ContrastSpec(
        cell_type=cell_type,
        cell_type_column=ct_col,
        group_column=group_col,
        reference_group=str(ref) if ref else None,
        comparison_group=str(comp) if comp else None,
        sample_column=sample_col,
    )
