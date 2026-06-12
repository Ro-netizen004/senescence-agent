# ── Deterministic pipeline ─────────────────────────────────────────────────
# QC → normalize → cluster runs exactly once per dataset.
# State stored in adata.uns so it survives cache retrieval.
# LLM never controls this — code does.

from tools.preprocessing import quality_control, normalize, check_required_metadata
from tools.clustering import cluster_cells


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

    # =========================
    # 0. LOCK RAW COUNTS (CRITICAL)
    # =========================
    if "counts" not in adata.layers:
        adata.layers["counts"] = adata.X.copy()
        print("OK Raw counts locked")

    # =========================
    # 1. QC
    # =========================
    if not state.get("qc"):
        print("Auto-running: quality_control")
        quality_control(adata, species)
        state["qc"] = True

    # =========================
    # 2. NORMALIZATION (VISUAL ONLY)
    # =========================
    if not state.get("norm"):
        print("Auto-running: normalize")
        normalize(adata)
        state["norm"] = True

    # =========================
    # 3. CLUSTERING
    # =========================
    if not state.get("cluster"):
        print("Auto-running: cluster_cells")
        cluster_cells(adata)
        state["cluster"] = True

    adata.uns["pipeline_state"] = state