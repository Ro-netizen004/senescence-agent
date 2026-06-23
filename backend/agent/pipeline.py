# ── Deterministic pipeline ─────────────────────────────────────────────────
# QC → normalize → cluster runs exactly once per dataset.
# State stored in adata.uns so it survives cache retrieval.
# LLM never controls this — code does.

import re

from tools.preprocessing import quality_control, normalize, check_required_metadata
from tools.clustering import cluster_cells

_AGE_CANDIDATES = [
    "age", "Age", "donor_age", "age_group", "timepoint",
    "time_point", "development_stage",
]
_CELL_TYPE_CANDIDATES = [
    "cell_ontology_class", "cell_type", "celltype",
    "Author_CellType", "Celltype", "cell_type_ontology_term_id",
    "ann_level_1", "annotation", "cell_annotation",
]
_SAMPLE_CANDIDATES = [
    "sample_id", "donor_id", "patient_id", "subject_id",
    "mouse.id", "mouse_id", "donor", "participant_id", "individual", "batch",
]


def _resolve_age_extremes(values: list) -> tuple:
    """Return (youngest, oldest, format_name) from a list of age value strings."""
    month_re = re.compile(r"^(\d+)m$", re.I)
    if all(month_re.match(v) for v in values):
        sv = sorted(values, key=lambda v: int(month_re.match(v).group(1)))
        return sv[0], sv[-1], "months_m"

    if all(re.match(r"^\d{1,3}$", v) for v in values):
        sv = sorted(values, key=int)
        return sv[0], sv[-1], "years_int"

    label_order = ["young", "juvenile", "adult", "middle", "old", "aged", "elderly"]
    lower_map = {v.lower(): v for v in values}
    matched = [l for l in label_order if l in lower_map]
    if len(matched) >= 2:
        return lower_map[matched[0]], lower_map[matched[-1]], "label"

    sv = sorted(values)
    return sv[0], sv[-1], "unknown"


def _infer_dataset_profile(adata, species: str) -> dict:
    obs = adata.obs

    age_col = next((c for c in _AGE_CANDIDATES if c in obs.columns), None)
    ct_col = next((c for c in _CELL_TYPE_CANDIDATES if c in obs.columns), None)
    sample_col = next((c for c in _SAMPLE_CANDIDATES if c in obs.columns), None)

    youngest = oldest = age_format = None
    age_values = []
    if age_col:
        age_values = sorted(obs[age_col].astype(str).unique().tolist())
        youngest, oldest, age_format = _resolve_age_extremes(age_values)

    profile = {
        "age_column": age_col,
        "age_format": age_format,
        "age_values": age_values,
        "youngest": youngest,
        "oldest": oldest,
        "cell_type_column": ct_col,
        "sample_column": sample_col,
        "species": species,
    }
    print(f"Dataset profile: age_col={age_col} ({age_format}), "
          f"ct_col={ct_col}, sample_col={sample_col}, "
          f"youngest={youngest}, oldest={oldest}")
    return profile


def _fix_gene_names(adata) -> None:
    """
    CellxGene datasets use Ensembl IDs (ENSMUSG...) as var_names
    but store gene symbols in var['feature_name']. Swap them so
    SenMayo gene matching works.
    """
    if adata.var_names[0].startswith("ENSMUSG") or adata.var_names[0].startswith("ENSG"):
        if "feature_name" in adata.var.columns:
            # Keep Ensembl IDs as a column for reference
            adata.var["ensembl_id"] = adata.var_names.copy()
            # Use gene symbols as var_names, make unique to avoid duplicates
            adata.var_names = adata.var["feature_name"].astype(str).values
            adata.var_names_make_unique()
            print(f"Converted Ensembl IDs → gene symbols (feature_name). "
                  f"Sample: {list(adata.var_names[:5])}")


def _fix_column_aliases(adata) -> None:
    """
    CellxGene uses different column names than original TMS Figshare files.
    Map them so all downstream tools work.
    """
    # cell_type → cell_ontology_class (used by senescence.py, age_analysis.py, agent.py)
    if "cell_ontology_class" not in adata.obs.columns and "cell_type" in adata.obs.columns:
        adata.obs["cell_ontology_class"] = adata.obs["cell_type"]
        print("Mapped column: cell_type → cell_ontology_class")

    # donor_id → sample_id (used by statistics.py, build_pseudobulk.py)
    if "sample_id" not in adata.obs.columns:
        for alt in ["donor_id", "mouse.id", "mouse_id", "batch"]:
            if alt in adata.obs.columns:
                adata.obs["sample_id"] = adata.obs[alt]
                print(f"Mapped column: {alt} → sample_id")
                break


def ensure_pipeline(adata, species: str) -> None:
    # Older builds set uns['log1p'] = True, which breaks Scanpy HVG (expects a dict).
    if adata.uns.get("log1p") is True:
        del adata.uns["log1p"]

    state = adata.uns.get("pipeline_state", {})
    if not isinstance(state, dict):
        state = {}

    # =========================
    # -1. FIX GENE NAMES + COLUMN ALIASES (before anything else)
    # =========================
    if not state.get("gene_names_fixed"):
        _fix_gene_names(adata)
        _fix_column_aliases(adata)
        state["gene_names_fixed"] = True

    if "metadata_status" not in adata.uns:
        adata.uns["metadata_status"] = check_required_metadata(adata)

    if "dataset_profile" not in adata.uns:
        adata.uns["dataset_profile"] = _infer_dataset_profile(adata, species)

    # Detect pre-processed datasets (e.g. TMS "processed official annotations"):
    # adata.raw present means adata.X is already log-normalized.
    already_normalized = adata.raw is not None

    # =========================
    # 0. LOCK RAW COUNTS (CRITICAL)
    # =========================
    if "counts" not in adata.layers:
        if already_normalized:
            # X is normalized — raw counts live in adata.raw.X
            import scipy.sparse as sp
            raw_X = adata.raw.X
            # Subset to current var (post-QC genes may differ from raw)
            if hasattr(adata.raw, 'var') and adata.raw.var is not None:
                shared = adata.var_names.intersection(adata.raw.var_names)
                raw_idx = adata.raw.var_names.get_indexer(shared)
                adata.layers["counts"] = raw_X[:, raw_idx]
            else:
                adata.layers["counts"] = raw_X
            print("Raw counts locked from adata.raw.X (pre-processed dataset)")
        else:
            adata.layers["counts"] = adata.X.copy()
            print("Raw counts locked from adata.X")

    # =========================
    # 1. QC
    # =========================
    if not state.get("qc"):
        if already_normalized:
            # Pre-processed dataset — QC already applied by original authors
            print("Skipping QC — dataset is pre-processed (adata.raw present)")
        else:
            print("Auto-running: quality_control")
            quality_control(adata, species)
        state["qc"] = True

    # =========================
    # 2. NORMALIZATION (VISUAL ONLY)
    # =========================
    if not state.get("norm"):
        if already_normalized:
            # adata.X is already log-normalized — do not normalize again
            adata.uns["senescence_agent_viz_normalized"] = True
            print("Skipping normalization — adata.X already log-normalized (adata.raw present)")
        else:
            print("Auto-running: normalize")
            normalize(adata)
        state["norm"] = True

    # =========================
    # 3. CLUSTERING
    # =========================
    if not state.get("cluster"):
        if "leiden" in adata.obs.columns:
            # Pre-computed clustering from original dataset — reuse it
            print("Skipping clustering — leiden already present in dataset")
        else:
            print("Auto-running: cluster_cells")
            cluster_cells(adata)
        state["cluster"] = True

    adata.uns["pipeline_state"] = state