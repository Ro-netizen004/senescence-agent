"""Exact fixed-panel raw-count slice from the official immutable S3 object."""
import json
import hashlib
from datetime import datetime, timezone
import h5py
import numpy as np
import pandas as pd
from scipy import sparse
from remote_feasibility import HTTPRangeReader, OUT, URL

TARGETS = ["ATP2A2", "CYB5R4", "ELOB", "GATA3", "KDM1A", "MED24", "MEN1", "NFKB2", "SGF29"]

def validate_counts(matrix):
    values = matrix.data
    if not np.isfinite(values).all() or (values < 0).any() or not np.equal(values, np.floor(values)).all():
        raise ValueError("not finite nonnegative integer counts")

def main():
    destination = OUT / "data"
    destination.mkdir(exist_ok=True)
    result_path = destination / "Stim8hr_panel_and_all_NTC_counts.npz"
    if result_path.exists():
        raise FileExistsError("preserve already extracted panel")
    obs = pd.read_csv(OUT / "sources/pseudobulk_obs.csv", index_col=0)
    var = pd.read_csv(OUT / "sources/pseudobulk_var.csv", index_col=0)
    selection = obs.culture_condition.eq("Stim8hr") & (obs.perturbed_gene_name.isin(TARGETS) | obs.guide_type.eq("non-targeting"))
    positions = np.flatnonzero(selection.to_numpy())
    expected = json.loads((OUT / "sources/REMOTE_RANGE_PROVENANCE.json").read_text())
    remote = HTTPRangeReader(URL, block_size=8*1024*1024)
    if remote.etag != expected["etag"] or remote.version != expected["version_id"] or remote.size != expected["bytes"]:
        raise ValueError("source changed since metadata acquisition")
    state = {"status":"STARTED", "url":URL, "source_bytes":remote.size, "source_etag":remote.etag,
             "source_version_id":remote.version, "started_at":datetime.now(timezone.utc).isoformat(),
             "selection":"Stim8hr; all nine fixed targets plus every non-targeting guide; no efficacy or DE filter",
             "source_full_file_sha256":None, "source_row_positions":positions.tolist()}
    try:
        with h5py.File(remote, "r") as source:
            X = source["X"]
            if X.attrs["encoding-type"] != "csr_matrix" or tuple(X.attrs["shape"]) != (len(obs), len(var)):
                raise ValueError("source shape/encoding mismatch")
            ptr = X["indptr"][:]
            breaks = np.flatnonzero(np.diff(positions) != 1) + 1
            runs = np.split(positions, breaks)
            blocks = []
            for i, run in enumerate(runs):
                start, stop = int(ptr[run[0]]), int(ptr[run[-1]+1])
                values = X["data"][start:stop]
                indices = X["indices"][start:stop]
                rowptr = ptr[run[0]:run[-1]+2] - start
                block = sparse.csr_matrix((values, indices, rowptr), shape=(len(run), len(var)))
                validate_counts(block)
                blocks.append(block)
                print(f"raw-count slice {i+1}/{len(runs)}: {len(run)} rows", flush=True)
        counts = sparse.vstack(blocks, format="csr")
        sums = np.asarray(counts.sum(axis=1)).ravel()
        selected = obs.iloc[positions].copy()
        if not np.array_equal(sums, selected.total_counts.to_numpy()):
            raise ValueError("actual count sums differ from source total_counts")
        counts = counts.astype(np.int64)
        sparse.save_npz(result_path, counts, compressed=True)
        selected.to_csv(destination / "Stim8hr_panel_and_all_NTC_obs.csv")
        var.to_csv(destination / "expression_genes.csv")
        state.update(status="VERIFIED_SELECTED_COUNTS", shape=list(counts.shape), nonzeros=int(counts.nnz),
                     raw_integer_check=True, all_row_sums_match_source=True,
                     selected_file_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),
                     selected_file_bytes=result_path.stat().st_size)
        for path in destination.iterdir():
            if path.is_file():
                path.chmod(0o444)
    except BaseException as exc:
        state.update(status="EXTRACTION_INCOMPLETE", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        state.update(finished_at=datetime.now(timezone.utc).isoformat(), ranges=remote.records,
                     requested_bytes=sum(r["end"]-r["start"]+1 for r in remote.records))
        sequence = len(list((OUT/"sources").glob("PANEL_EXTRACTION_*.json")))+1
        (OUT/f"sources/PANEL_EXTRACTION_{sequence:02d}.json").write_text(json.dumps(state, indent=2)+"\n")

if __name__ == "__main__":
    main()
