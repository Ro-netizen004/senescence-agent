# ── Deterministic pipeline ─────────────────────────────────────────────────
# QC → normalize → cluster runs exactly once per dataset.
# State stored in adata.uns so it survives cache retrieval.
# LLM never controls this — code does.

from tools.preprocessing import quality_control, normalize
from tools.clustering import cluster_cells

def ensure_pipeline(adata, species: str) -> None:
    """
    Guarantee preprocessing runs in correct order exactly once.
    Called automatically before any LLM tool execution.

    Uses adata.uns["pipeline_state"] for safe persistence —
    this survives cache lookups unlike Python object attributes.
    """
    state = adata.uns.get("pipeline_state", {})

    if not state.get("qc"):
        print("Auto-running: quality_control")
        quality_control(adata, species)
        state["qc"] = True

    if not state.get("norm"):
        print("Auto-running: normalize")
        normalize(adata)
        state["norm"] = True

    if not state.get("cluster"):
        print("Auto-running: cluster_cells")
        cluster_cells(adata)
        state["cluster"] = True

    adata.uns["pipeline_state"] = state