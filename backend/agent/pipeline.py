# ── Deterministic pipeline ─────────────────────────────────────────────────
# QC → normalize → cluster runs exactly once per dataset.
# State stored in adata.uns so it survives cache retrieval.
# LLM never controls this — code does.

from tools.preprocessing import quality_control, normalize, check_required_metadata
from tools.clustering import cluster_cells

def ensure_pipeline(adata, species: str) -> None:
    # Older builds set uns['log1p'] = True, which breaks Scanpy HVG (expects a dict).
    if adata.uns.get("log1p") is True:
        del adata.uns["log1p"]

    state = adata.uns.get("pipeline_state", {})
    if not isinstance(state, dict):
        state = {}

    if "metadata_status" not in adata.uns:
        adata.uns["metadata_status"] = check_required_metadata(adata)

    # =========================
    # 0. LOCK RAW COUNTS (CRITICAL)
    # =========================
    if "counts" not in adata.layers:
        adata.layers["counts"] = adata.X.copy()
        print("✔ Raw counts locked")

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