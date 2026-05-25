import scanpy as sc


# =========================================================
# 1. QUALITY CONTROL
# =========================================================

def quality_control(adata, species: str = "mouse"):
    """
    Basic QC filtering.
    Safe to rerun (idempotent).
    """

    if adata.obs.get("qc_done", False) is True:
        print("⚠ QC already applied — skipping.")
        return adata, species

    print(f"Before QC: {adata.shape[0]} cells, {adata.shape[1]} genes")
    print(f"Species: {species}")

    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)

    adata.obs["qc_done"] = True

    print(f"After QC: {adata.shape[0]} cells, {adata.shape[1]} genes")

    return adata, species


# =========================================================
# 2. MITOCHONDRIAL FILTERING (PUBLICATION STANDARD)
# =========================================================

def add_mito_qc(adata, species: str = "mouse", threshold: float = 20):
    """
    Removes low-quality / dying cells based on mitochondrial content.
    """

    mito_prefix = "mt-" if species == "mouse" else "MT-"

    adata.var["mt"] = adata.var_names.str.startswith(mito_prefix)

    sc.pp.calculate_qc_metrics(
        adata,
        qc_vars=["mt"],
        inplace=True
    )

    adata = adata[adata.obs["pct_counts_mt"] < threshold].copy()

    print(f"After mito filter: {adata.shape[0]} cells")

    return adata


# =========================================================
# 3. RAW COUNT LOCK (CRITICAL FOR DESEQ2 / PSEUDOBULK)
# =========================================================

def lock_raw_counts(adata):
    """
    Stores raw counts for statistical inference.
    NEVER uses normalized data.
    """

    if "counts" in adata.layers:
        print("Raw counts already locked.")
        return adata

    if adata.raw is not None:
        adata.layers["counts"] = adata.raw.X.copy()
        print("Raw counts locked from adata.raw.X")
        return adata

    raise ValueError(
        " No raw counts found. Must have adata.raw.X or pre-existing adata.layers['counts']"
    )


# =========================================================
# 4. NORMALIZATION (VISUALIZATION ONLY)
# =========================================================

def normalize(adata):
    """
    Log-normalization for UMAP / clustering / plots ONLY.
    NOT for DESeq2 or pseudobulk.
    """

    if adata.uns.get("senescence_agent_viz_normalized"):
        print("Normalization already applied — skipping.")
        return adata

    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    # Do not set adata.uns["log1p"] = True — Scanpy stores a dict there and HVG breaks if overwritten.
    adata.uns["senescence_agent_viz_normalized"] = True

    print("Normalization complete (visualization layer only)")

    return adata


# =========================================================
# 5. METADATA VALIDATION (PSEUDOBULK SAFE)
# =========================================================

def check_required_metadata(
    adata,
    required=("age", "cell_ontology_class", "sample_id")
):
    """
    Ensures pseudobulk readiness.
    Uses fallback mapping instead of crashing.
    """

    missing = [r for r in required if r not in adata.obs.columns]

    # fallback mappings for real datasets
    alternatives = {
        "sample_id": ["mouse.id", "mouse_id", "donor_id", "batch"]
    }

    for col in missing[:]:
        for alt in alternatives.get(col, []):
            if alt in adata.obs.columns:
                adata.obs[col] = adata.obs[alt]
                print(f"Using '{alt}' as '{col}'")
                missing.remove(col)
                break

    if missing:
        print(f"WARNING: Missing metadata: {missing}")
        print("WARNING: Pseudobulk will be degraded (no true biological replicates)")
        return {
            "status": "degraded",
            "missing": missing
        }

    print("Metadata validation passed")

    return {"status": "ok"}


# =========================================================
# 6. PIPELINE VALIDATION (SAFETY CHECK)
# =========================================================

def validate_pipeline(adata):
    """
    Ensures dataset is safe for statistical inference.
    """

    if "counts" not in adata.layers:
        raise ValueError(
            "Pipeline invalid: missing raw counts in adata.layers['counts']"
        )

    print("Pipeline validation passed")

    return True


# =========================================================
# 7. FULL PIPELINE WRAPPER (OPTIONAL)
# =========================================================

def run_preprocessing_pipeline(adata, species: str = "mouse"):
    """
    One-call preprocessing pipeline for your agent.
    """

    adata, species = quality_control(adata, species)
    adata = add_mito_qc(adata, species)
    adata = lock_raw_counts(adata)
    adata = normalize_for_visualization(adata)

    validate_pipeline(adata)

    return adata, species
