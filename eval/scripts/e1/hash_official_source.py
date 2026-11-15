"""Compute full official object SHA-256 by streaming; no whole-file disk copy."""
import hashlib
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from remote_feasibility import OUT, URL

def main():
    destination = OUT / "sources/OFFICIAL_FULL_FILE_SHA256.json"
    if destination.exists():
        raise FileExistsError(destination)
    baseline = json.loads((OUT/"sources/REMOTE_RANGE_PROVENANCE.json").read_text())
    state = {"status":"IN_PROGRESS", "url":URL, "expected_bytes":baseline["bytes"],
             "etag":baseline["etag"], "version_id":baseline["version_id"],
             "started_at":datetime.now(timezone.utc).isoformat(),
             "full_file_stored_locally":False, "method":"single sequential GET with If-Match; SHA-256 over every byte"}
    digest = hashlib.sha256()
    total = 0
    try:
        with urlopen(Request(URL, headers={"If-Match":baseline["etag"]}), timeout=90) as response:
            if response.headers["ETag"] != baseline["etag"] or int(response.headers["Content-Length"]) != baseline["bytes"]:
                raise ValueError("official source identity changed")
            while True:
                data = response.read(16*1024*1024)
                if not data:
                    break
                digest.update(data)
                total += len(data)
                if total % (512*1024*1024) == 0:
                    print(f"verified stream progress {total}/{baseline['bytes']} bytes", flush=True)
        if total != baseline["bytes"]:
            raise ValueError("incomplete source stream")
        state.update(status="VERIFIED", sha256=digest.hexdigest())
    except BaseException as exc:
        state.update(status="INCOMPLETE", error_type=type(exc).__name__, error=str(exc), sha256=None)
        raise
    finally:
        state.update(bytes_read=total, finished_at=datetime.now(timezone.utc).isoformat())
        destination.write_text(json.dumps(state,indent=2)+"\n")
    print(json.dumps(state),flush=True)

if __name__ == "__main__":
    main()
