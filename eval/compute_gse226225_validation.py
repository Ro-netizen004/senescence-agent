"""
GSE226225 Validation: SenMayo scoring vs published senescence labels.

Dataset: WI-38 human fibroblasts
Conditions: CTRL (proliferating), RS (replicative senescence),
            IR (irradiation), ETO (etoposide-induced)
Species: human
Gene names: gene symbols (CDKN1A, CDKN2A, etc.)

Usage:
    backend\\venv\\Scripts\\python.exe eval\\compute_gse226225_validation.py

Requires: GSE226225_RAW.tar extracted under backend/data/validation/
"""

import json
import os
import sys
import tarfile
import gzip
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── Setup paths ──────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from agent.pipeline import ensure_pipeline, _fix_gene_names, _fix_column_aliases
from tools.senescence import senescence_score, find_senescence_markers

DATA_DIR = ROOT / "backend" / "data" / "validation"
OUT_DIR = ROOT / "eval" / "results" / "validation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TAR_PATH = DATA_DIR / "GSE226225_RAW.tar"
H5AD_PATH = DATA_DIR / "GSE226225.h5ad"
SPECIES = "human"


# ── Step 1: Extract and build AnnData ────────────────────────────────────

def extract_tar():
    """Extract the tar file and find sample directories."""
    extract_dir = DATA_DIR / "extracted"
    if extract_dir.exists() and any(extract_dir.iterdir()):
        print(f"Already extracted to {extract_dir}")
        return extract_dir

    print(f"Extracting {TAR_PATH}...")
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(TAR_PATH, "r") as tar:
        tar.extractall(extract_dir)
    print(f"Extracted to {extract_dir}")
    return extract_dir


def find_sample_dirs(extract_dir: Path) -> list:
    """Find all sample directories with matrix.mtx, barcodes.tsv, features/genes.tsv."""
    samples = []

    # GEO format: individual .gz files like GSM123_barcodes.tsv.gz, GSM123_matrix.mtx.gz
    gz_files = list(extract_dir.rglob("*.gz"))
    if gz_files:
        # Group by sample prefix
        prefixes = set()
        for f in gz_files:
            name = f.name
            # Pattern: GSM7081795_CTRL_barcodes.tsv.gz
            for suffix in ["_barcodes.tsv.gz", "_matrix.mtx.gz", "_features.tsv.gz", "_genes.tsv.gz"]:
                if name.endswith(suffix):
                    prefix = name[:-len(suffix)]
                    prefixes.add(prefix)

        for prefix in sorted(prefixes):
            sample = {"prefix": prefix, "dir": extract_dir}

            # Find the actual files
            for f in gz_files:
                name = f.name
                if name.startswith(prefix):
                    if "barcodes" in name:
                        sample["barcodes"] = f
                    elif "matrix" in name:
                        sample["matrix"] = f
                    elif "features" in name or "genes" in name:
                        sample["features"] = f

            if "barcodes" in sample and "matrix" in sample and "features" in sample:
                samples.append(sample)
                print(f"  Found sample: {prefix}")

    # Also check for subdirectories with standard 10x format
    for d in extract_dir.iterdir():
        if d.is_dir():
            mtx = list(d.glob("matrix.mtx*"))
            barcodes = list(d.glob("barcodes.tsv*"))
            features = list(d.glob("features.tsv*")) or list(d.glob("genes.tsv*"))
            if mtx and barcodes and features:
                samples.append({
                    "prefix": d.name,
                    "dir": d,
                    "matrix": mtx[0],
                    "barcodes": barcodes[0],
                    "features": features[0],
                })
                print(f"  Found sample dir: {d.name}")

    return samples


def decompress_gz(gz_path: Path, out_dir: Path) -> Path:
    """Decompress a .gz file to out_dir, return path to decompressed file."""
    out_name = gz_path.name[:-3]  # remove .gz
    out_path = out_dir / out_name
    if out_path.exists():
        return out_path
    with gzip.open(gz_path, "rb") as f_in:
        with open(out_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    return out_path


def load_sample(sample: dict, tmp_dir: Path) -> sc.AnnData:
    """Load one sample from GEO files into AnnData."""
    # Create a temp directory for this sample's decompressed files
    sample_dir = tmp_dir / sample["prefix"]
    sample_dir.mkdir(parents=True, exist_ok=True)

    # Decompress if needed
    matrix_path = sample["matrix"]
    barcodes_path = sample["barcodes"]
    features_path = sample["features"]

    if str(matrix_path).endswith(".gz"):
        matrix_path = decompress_gz(matrix_path, sample_dir)
    if str(barcodes_path).endswith(".gz"):
        barcodes_path = decompress_gz(barcodes_path, sample_dir)
    if str(features_path).endswith(".gz"):
        features_path = decompress_gz(features_path, sample_dir)

    # Rename to standard 10x names for sc.read_10x_mtx
    std_dir = sample_dir / "10x"
    std_dir.mkdir(exist_ok=True)

    # Copy with standard names
    shutil.copy2(matrix_path, std_dir / "matrix.mtx")
    shutil.copy2(barcodes_path, std_dir / "barcodes.tsv")

    # features or genes
    feat_dest = std_dir / "genes.tsv"
    shutil.copy2(features_path, feat_dest)

    # Try reading
    try:
        adata = sc.read_10x_mtx(str(std_dir), var_names="gene_symbols", make_unique=True)
    except Exception:
        # Try with gene_ids
        try:
            adata = sc.read_10x_mtx(str(std_dir), var_names="gene_ids", make_unique=True)
        except Exception as e:
            print(f"  Failed to read {sample['prefix']}: {e}")
            return None

    # Extract condition from prefix (e.g., GSM7081795_CTRL -> CTRL)
    prefix = sample["prefix"]
    parts = prefix.split("_", 1)
    condition = parts[1] if len(parts) > 1 else prefix

    adata.obs["sample_id"] = prefix
    adata.obs["condition"] = condition
    adata.obs_names = [f"{prefix}_{bc}" for bc in adata.obs_names]

    print(f"  Loaded {prefix}: {adata.shape[0]} cells, {adata.shape[1]} genes, condition={condition}")
    return adata


def build_combined_h5ad():
    """Build combined AnnData from all samples."""
    if H5AD_PATH.exists():
        print(f"Loading existing {H5AD_PATH}")
        return sc.read_h5ad(str(H5AD_PATH))

    extract_dir = extract_tar()
    samples = find_sample_dirs(extract_dir)

    if not samples:
        print("ERROR: No samples found! Listing extracted files:")
        for f in sorted(extract_dir.rglob("*"))[:50]:
            print(f"  {f}")
        sys.exit(1)

    tmp_dir = DATA_DIR / "tmp_decompress"
    tmp_dir.mkdir(exist_ok=True)

    adatas = []
    for s in samples:
        ad = load_sample(s, tmp_dir)
        if ad is not None:
            adatas.append(ad)

    if not adatas:
        print("ERROR: No samples loaded successfully!")
        sys.exit(1)

    print(f"\nConcatenating {len(adatas)} samples...")
    combined = sc.concat(adatas, join="inner")
    combined.var_names_make_unique()

    print(f"Combined: {combined.shape[0]} cells, {combined.shape[1]} genes")
    print(f"Conditions: {combined.obs['condition'].value_counts().to_dict()}")

    # Save
    combined.write_h5ad(str(H5AD_PATH))
    print(f"Saved to {H5AD_PATH}")

    # Cleanup tmp
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return combined


# ── Step 2: Inspect and find label column ────────────────────────────────

def inspect_dataset(adata):
    """Print dataset info and find senescence label column."""
    print("\n" + "=" * 60)
    print("DATASET INSPECTION")
    print("=" * 60)
    print(f"Shape: {adata.shape[0]} cells x {adata.shape[1]} genes")
    print(f"Columns: {list(adata.obs.columns)}")
    print(f"\nCondition values:")
    print(adata.obs["condition"].value_counts())
    print(f"\nFirst 20 gene names: {list(adata.var_names[:20])}")

    # Check gene name style
    if adata.var_names[0].startswith("ENSG"):
        print("\nGene naming: Ensembl IDs (need conversion)")
    elif adata.var_names[0].isupper():
        print("\nGene naming: Human symbols (UPPERCASE)")
    else:
        print(f"\nGene naming: {adata.var_names[0]} style")

    # Check for SenMayo key genes
    key_genes = ["CDKN1A", "CDKN2A", "IL6", "MKI67", "TP53", "LMNB1", "SERPINE1", "GLB1"]
    found = [g for g in key_genes if g in adata.var_names]
    print(f"\nKey senescence genes found: {found}")
    print(f"Key genes missing: {[g for g in key_genes if g not in adata.var_names]}")

    return adata


# ── Step 3: Define senescence labels ────────────────────────────────────

def assign_senescence_labels(adata):
    """
    GSE226225 labels:
    - CTRL = proliferating (non-senescent)
    - RS = replicative senescence (senescent)
    - IR = irradiation-induced senescence (senescent)
    - ETO with timepoints: ETO-day0 = control, later timepoints = senescent

    We label: any condition containing RS, IR, or ETO (except day0) as senescent.
    """
    condition = adata.obs["condition"].astype(str)

    # Non-senescent: CTRL samples and ETO day 0 (treatment not yet active)
    is_control = (
        condition.str.upper().str.contains("CTRL") |
        condition.str.contains("day_0", case=False) |
        condition.str.contains("day0", case=False) |
        condition.str.contains("d0", case=False)
    )

    # Senescent: RS, IR, and ETO timepoints (day 1+)
    senescent = ~is_control

    adata.obs["published_senescent"] = senescent
    adata.obs["senescence_label"] = senescent.map({True: "senescent", False: "non-senescent"})

    print(f"\nSenescence labels assigned:")
    print(adata.obs["senescence_label"].value_counts())
    print(f"\nLabel by condition:")
    cross = pd.crosstab(adata.obs["condition"], adata.obs["senescence_label"])
    print(cross)

    return "published_senescent"


# ── Step 4: Run SenMayo scoring ──────────────────────────────────────────

def run_scoring(adata):
    """Run SenMayo scoring and return results."""
    print("\n" + "=" * 60)
    print("RUNNING SENMAYO SCORING")
    print("=" * 60)

    # Fix gene names if needed
    _fix_gene_names(adata)
    _fix_column_aliases(adata)

    # Run pipeline (QC, norm, cluster)
    ensure_pipeline(adata, SPECIES)

    # Run marker detection
    marker_result = find_senescence_markers(adata, species=SPECIES)
    print(f"\nSenMayo coverage: {marker_result['coverage_pct']}%")
    print(f"Found: {len(marker_result['found_markers'])} genes")

    # Run scoring
    score_result = senescence_score(adata, species=SPECIES)
    print(f"\nScoring complete.")
    print(f"Genes used: {score_result.get('genes_used')}")
    print(f"Mean score: {score_result.get('mean_score')}")

    return marker_result, score_result


# ── Step 5: Compute validation metrics ───────────────────────────────────

def compute_metrics(adata, published_col: str, score_result: dict, marker_result: dict):
    """Compute precision, sensitivity, F1 for SenMayo vs published labels."""
    print("\n" + "=" * 60)
    print("COMPUTING VALIDATION METRICS")
    print("=" * 60)

    true_senescent = adata.obs[published_col].astype(bool)
    scores = adata.obs["senescence_score"]

    # Top 25% threshold
    threshold = np.percentile(scores, 75)
    pred = scores >= threshold

    tp = int((pred & true_senescent).sum())
    fp = int((pred & ~true_senescent).sum())
    fn = int((~pred & true_senescent).sum())
    tn = int((~pred & ~true_senescent).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0
    sensitivity = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * sensitivity / (precision + sensitivity) if (precision + sensitivity) else 0

    metrics = {
        "dataset": "GSE226225",
        "species": SPECIES,
        "published_label_column": published_col,
        "label_definition": "CTRL/day0 = non-senescent; RS/IR/ETO timepoints = senescent",
        "threshold": "top_25_percent_senmayo_score",
        "threshold_value": round(float(threshold), 4),
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "true_senescent": int(true_senescent.sum()),
        "true_non_senescent": int((~true_senescent).sum()),
        "predicted_senescent": int(pred.sum()),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "sensitivity": round(sensitivity, 4),
        "f1": round(f1, 4),
        "senmayo_coverage_pct": marker_result.get("coverage_pct"),
        "genes_used": score_result.get("genes_used"),
    }

    print(f"\n  Threshold (75th percentile): {threshold:.4f}")
    print(f"  True senescent: {true_senescent.sum()}")
    print(f"  Predicted senescent: {pred.sum()}")
    print(f"  TP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Sensitivity: {sensitivity:.4f}")
    print(f"  F1: {f1:.4f}")

    # Save
    out_path = OUT_DIR / "gse226225_metrics.json"
    out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nSaved: {out_path}")

    return metrics


# ── Step 6: UMAP figure ─────────────────────────────────────────────────

def make_umap(adata, published_col: str):
    """Generate UMAP colored by score, published label, and prediction."""
    print("\nGenerating UMAP figure...")

    threshold = np.percentile(adata.obs["senescence_score"], 75)
    adata.obs["predicted_senescent"] = (adata.obs["senescence_score"] >= threshold).map(
        {True: "Predicted senescent", False: "Predicted non-senescent"}
    )
    adata.obs["published_label_display"] = adata.obs[published_col].map(
        {True: "Published senescent", False: "Published non-senescent"}
    )

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    sc.pl.umap(adata, color="senescence_score", ax=axes[0], show=False,
               cmap="Reds", title="SenMayo Score")
    sc.pl.umap(adata, color="published_label_display", ax=axes[1], show=False,
               title="Published Labels")
    sc.pl.umap(adata, color="predicted_senescent", ax=axes[2], show=False,
               title="SenMayo Prediction (top 25%)")

    plt.tight_layout()
    out_path = OUT_DIR / "gse226225_umap.png"
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")


# ── Step 7: Single-marker comparison ────────────────────────────────────

def compare_markers(adata, published_col: str):
    """Compare SenMayo vs CDKN2A-only vs MKI67-absence."""
    print("\n" + "=" * 60)
    print("MARKER COMPARISON")
    print("=" * 60)

    true_senescent = adata.obs[published_col].astype(bool)
    rows = []

    def calc(name, pred):
        pred = pred.astype(bool)
        tp = int((pred & true_senescent).sum())
        fp = int((pred & ~true_senescent).sum())
        fn = int((~pred & true_senescent).sum())
        sens = tp / (tp + fn) if (tp + fn) else 0
        prec = tp / (tp + fp) if (tp + fp) else 0
        f1_val = 2 * prec * sens / (prec + sens) if (prec + sens) else 0
        rows.append({
            "method": name,
            "sensitivity": round(sens, 4),
            "precision": round(prec, 4),
            "f1": round(f1_val, 4),
            "tp": tp, "fp": fp, "fn": fn,
        })
        print(f"  {name}: sens={sens:.4f}, prec={prec:.4f}, f1={f1_val:.4f}")

    # Method A: CDKN2A threshold (median)
    cdkn2a_gene = "CDKN2A" if "CDKN2A" in adata.var_names else "Cdkn2a"
    if cdkn2a_gene in adata.var_names:
        expr = adata[:, cdkn2a_gene].X
        if hasattr(expr, "toarray"):
            expr = expr.toarray()
        expr = expr.flatten()
        pred_a = expr > np.median(expr)
        calc("CDKN2A (p16) only", pred_a)
    else:
        print(f"  CDKN2A not found in var_names, skipping")

    # Method B: MKI67 absence
    mki67_gene = "MKI67" if "MKI67" in adata.var_names else "Mki67"
    if mki67_gene in adata.var_names:
        expr = adata[:, mki67_gene].X
        if hasattr(expr, "toarray"):
            expr = expr.toarray()
        expr = expr.flatten()
        pred_b = expr == 0
        calc("MKI67 absence", pred_b)
    else:
        print(f"  MKI67 not found in var_names, skipping")

    # Method C: SenMayo top 25%
    threshold = np.percentile(adata.obs["senescence_score"], 75)
    pred_c = adata.obs["senescence_score"].values >= threshold
    calc("SenMayo (ours)", pred_c)

    # Save
    df = pd.DataFrame(rows)
    out_path = OUT_DIR / "marker_comparison.csv"
    df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")
    print(f"\n{df.to_markdown(index=False)}")

    return df


# ── Step 8: Generate report ──────────────────────────────────────────────

def write_report(metrics: dict, comparison_df):
    """Write the final validation report."""
    comp_table = comparison_df.to_markdown(index=False) if comparison_df is not None else "Not available"

    report = f"""# GSE226225 Validation Report

## Dataset
- **Source:** GEO GSE226225
- **Shape:** {metrics['n_cells']} cells x {metrics['n_genes']} genes
- **Species:** {metrics['species']} (WI-38 fibroblasts)
- **Label column:** {metrics['published_label_column']}
- **Label definition:** {metrics['label_definition']}
- **Gene naming:** Human symbols (CDKN1A, CDKN2A, etc.)

## SenMayo Results
- **Coverage:** {metrics['senmayo_coverage_pct']}% ({metrics['genes_used']} genes used)
- **Threshold:** Top 25% of SenMayo scores (value: {metrics['threshold_value']})
- **Sensitivity:** {metrics['sensitivity']:.1%}
- **Precision:** {metrics['precision']:.1%}
- **F1 Score:** {metrics['f1']:.1%}

### Confusion Matrix
|  | Predicted Senescent | Predicted Non-senescent |
|--|--:|--:|
| **True Senescent** | {metrics['tp']} (TP) | {metrics['fn']} (FN) |
| **True Non-senescent** | {metrics['fp']} (FP) | {metrics['tn']} (TN) |

## Marker Comparison

{comp_table}

## UMAP
See `gse226225_umap.png` for side-by-side comparison of:
1. SenMayo score distribution
2. Published senescence labels
3. SenMayo top-25% predictions

## Notes / Limitations
- **Label interpretation:** CTRL cells are labeled non-senescent; RS, IR, and ETO-treated cells are labeled senescent. ETO day-0 is treated as non-senescent (treatment not yet active).
- **Threshold choice:** Top 25% is a simple first-pass threshold. AUROC/AUPRC would give a threshold-independent evaluation.
- **Cell type:** All cells are WI-38 fibroblasts (single cell type), so cell-type confounding is not an issue.
- **SenMayo coverage:** Not all 125 SenMayo genes may be expressed in WI-38 fibroblasts.
"""

    out_path = OUT_DIR / "gse226225_report.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved: {out_path}")


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("GSE226225 VALIDATION PIPELINE")
    print("=" * 60)

    # Step 1: Load/build dataset
    adata = build_combined_h5ad()

    # Step 2: Inspect
    inspect_dataset(adata)

    # Step 3: Assign labels
    published_col = assign_senescence_labels(adata)

    # Step 4: Run SenMayo scoring
    marker_result, score_result = run_scoring(adata)

    # Step 5: Compute metrics
    metrics = compute_metrics(adata, published_col, score_result, marker_result)

    # Step 6: UMAP
    try:
        make_umap(adata, published_col)
    except Exception as e:
        print(f"UMAP generation failed: {e}")

    # Step 7: Marker comparison
    try:
        comparison_df = compare_markers(adata, published_col)
    except Exception as e:
        print(f"Marker comparison failed: {e}")
        comparison_df = None

    # Step 8: Report
    write_report(metrics, comparison_df)

    print("\n" + "=" * 60)
    print("VALIDATION COMPLETE")
    print("=" * 60)
    print(f"\nOutputs in: {OUT_DIR}")
    print(f"  gse226225_metrics.json")
    print(f"  gse226225_report.md")
    print(f"  gse226225_umap.png")
    print(f"  marker_comparison.csv")


if __name__ == "__main__":
    main()
