"""E1-S paths and preservation helpers; no access to credential files."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
E1=ROOT/"eval/results/v2/e1/e1_v2_1_20261022_01"
OUT=ROOT/"eval/results/v2/e1s/e1s_v1_20261023_01"
TARGETS=["ATP2A2","CYB5R4","ELOB","GATA3","KDM1A","MED24","MEN1","NFKB2","SGF29"]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def clean(x):
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

def write(path,value):
    with Path(path).open("x") as f:json.dump(clean(value),f,indent=2,allow_nan=False);f.write("\n")

def original_check():
    manifest=E1/"E1_SHA256_MANIFEST.json"
    expected=json.loads(manifest.read_text())["files"]
    mismatches=[p for p,h in expected.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    # Independently verify the older baseline too, without rewriting E1's audit.
    old=json.loads((E1/"FROZEN_BASELINE.json").read_text())
    old_bad=[p for p,h in old.items() if not (ROOT/p).is_file() or sha(ROOT/p)!=h]
    return {"e1_manifest_sha256":sha(manifest),"e1_files":len(expected),"e1_mismatches":mismatches,
            "prior_frozen_files":len(old),"prior_mismatches":old_bad,
            "paired_fit_files":len(list((E1/"execution").glob("*/paired_sensitivity/*.csv")))}

def verify_lock():
    lock=json.loads((OUT/"E1S_PROTOCOL_LOCK.json").read_text())
    for p,h in lock["files"].items():
        if sha(ROOT/p)!=h:raise ValueError("E1-S locked file changed: "+p)
    result=original_check()
    if result["e1_mismatches"] or result["prior_mismatches"]:raise ValueError("Frozen source changed")
    return lock
