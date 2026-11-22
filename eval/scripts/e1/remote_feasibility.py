"""Read official HDF5 bytes with conditional HTTP ranges; no DE or model calls."""
import io
import json
import hashlib
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import h5py
import pandas as pd
from anndata._io.specs import read_elem

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "eval/results/v2/e1/e1_v2_1_20261022_01"
URL = "https://genome-scale-tcell-perturb-seq.s3.amazonaws.com/marson2025_data/GWCD4i.pseudobulk_merged.h5ad"

class HTTPRangeReader(io.RawIOBase):
    def __init__(self, url, block_size=1024 * 1024):
        self.url = url
        self.block_size = block_size
        self.position = 0
        self.cache = OrderedDict()
        self.records = []
        with urlopen(Request(url, method="HEAD"), timeout=40) as response:
            self.size = int(response.headers["Content-Length"])
            self.etag = response.headers["ETag"]
            self.modified = response.headers.get("Last-Modified")
            self.version = response.headers.get("x-amz-version-id")

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        if position < 0:
            raise ValueError("negative seek")
        self.position = position
        return position

    def readinto(self, buffer):
        value = self.read(len(buffer))
        buffer[:len(value)] = value
        return len(value)

    def read(self, size=-1):
        end = self.size if size < 0 else min(self.size, self.position + size)
        pieces = []
        while self.position < end:
            block = self.position // self.block_size
            if block not in self.cache:
                start = block * self.block_size
                stop = min(self.size, start + self.block_size) - 1
                request = Request(self.url, headers={"Range": f"bytes={start}-{stop}", "If-Match": self.etag})
                with urlopen(request, timeout=60) as response:
                    if response.status != 206 or response.headers.get("Content-Range") != f"bytes {start}-{stop}/{self.size}":
                        raise IOError("server did not honor exact requested range")
                    data = response.read()
                    if len(data) != stop - start + 1 or response.headers["ETag"] != self.etag:
                        raise IOError("source identity/length mismatch")
                self.cache[block] = data
                self.records.append({"start": start, "end": stop, "sha256": hashlib.sha256(data).hexdigest()})
                if len(self.cache) > 128:
                    self.cache.popitem(last=False)
            data = self.cache[block]
            offset = self.position % self.block_size
            n = min(end - self.position, len(data) - offset)
            pieces.append(data[offset:offset+n])
            self.position += n
        return b"".join(pieces)


def main():
    remote = HTTPRangeReader(URL)
    try:
        with h5py.File(remote, "r") as source:
            if (OUT / "sources/pseudobulk_obs.csv").exists():
                obs = pd.read_csv(OUT / "sources/pseudobulk_obs.csv", index_col=0)
                var = pd.read_csv(OUT / "sources/pseudobulk_var.csv", index_col=0)
            else:
                obs = read_elem(source["obs"])
                var = read_elem(source["var"])
                obs.to_csv(OUT / "sources/pseudobulk_obs.csv")
                var.to_csv(OUT / "sources/pseudobulk_var.csv")
            structure = {}
            def visit(name, item):
                structure[name] = {"kind": type(item).__name__, "shape": list(item.shape) if isinstance(item, h5py.Dataset) else None,
                                   "dtype": str(item.dtype) if isinstance(item, h5py.Dataset) else None,
                                   "attrs": {str(k): str(v) for k, v in item.attrs.items()}}
            for name in ["X", "layers"]:
                if name in source:
                    item = source[name]
                    visit(name, item)
                    if isinstance(item, h5py.Group):
                        for key in item.keys():
                            visit(name + "/" + key, item[key])
            (OUT / "sources/HDF5_STRUCTURE.json").write_text(json.dumps(structure, indent=2) + "\n")
            print("obs", obs.shape, "var", var.shape, flush=True)
            print("columns", obs.columns.tolist(), flush=True)
            print("X", structure.get("X"), flush=True)
    finally:
        provenance = {"url": URL, "bytes": remote.size, "etag": remote.etag,
                      "last_modified": remote.modified, "version_id": remote.version,
                      "retrieved_at": datetime.now(timezone.utc).isoformat(),
                      "full_file_sha256": None, "full_file_staged": False,
                      "range_requests": remote.records, "requested_bytes": sum(r["end"]-r["start"]+1 for r in remote.records)}
        sequence = len(list((OUT / "sources").glob("REMOTE_RANGE_PROVENANCE*.json"))) + 1
        (OUT / f"sources/REMOTE_RANGE_PROVENANCE_{sequence:02d}.json").write_text(json.dumps(provenance, indent=2) + "\n")

if __name__ == "__main__":
    main()
