"""Evaluation-only E2 helpers. Never read credential files or historical replies."""
import hashlib
import json
import math
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'eval/results/v2/e2/e2_v1_20261023_01'
E1 = ROOT / 'eval/results/v2/e1/e1_v2_1_20261022_01'
E1S = ROOT / 'eval/results/v2/e1s/e1s_v1_20261023_01'
C3 = ROOT / 'eval/results/task3c/reproduction_v1_attempt3_20261007_01'
MODEL = 'gemini-3.5-flash'
TARGETS = ['ATP2A2','CYB5R4','ELOB','GATA3','KDM1A','MED24','MEN1','NFKB2','SGF29']

def now(): return datetime.now(timezone.utc).isoformat()
def read(p): return json.loads(Path(p).read_text())
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def clean(x):
    if isinstance(x,dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)): return [clean(v) for v in x]
    if hasattr(x,'item'): return clean(x.item())
    if isinstance(x,float) and not math.isfinite(x): return None
    return x
def encode(x): return json.dumps(clean(x),sort_keys=True,allow_nan=False,ensure_ascii=False)
def digest(x): return hashlib.sha256(encode(x).encode()).hexdigest()
def write(p,x):
    with Path(p).open('x') as f: f.write(json.dumps(clean(x),indent=2,allow_nan=False)+'\n')
def textfile(p,s):
    with Path(p).open('x') as f: f.write(s)
def rel(p): return str(Path(p).relative_to(ROOT))

def preservation():
    records=[]
    for p in [E1/'E1_SHA256_MANIFEST.json',E1S/'E1S_SHA256_MANIFEST.json',
              C3/'SHA256_MANIFEST.json',ROOT/'eval/results/task3d/human_annotation_v1_20261022_01/TASK3D_SHA256_MANIFEST.json']:
        m=read(p)['files']
        entries=m.items() if isinstance(m,dict) else [(str((p.parent/r['path']).relative_to(ROOT)),r['sha256']) for r in m]
        entries=list(entries)
        bad=[n for n,h in entries if not (ROOT/n).is_file() or sha(ROOT/n)!=h]
        records.append({'manifest':rel(p),'sha256':sha(p),'entries':len(entries),'mismatches':bad})
    m=read(E1/'FROZEN_BASELINE.json')
    records.append({'manifest':rel(E1/'FROZEN_BASELINE.json'),'entries':len(m),
                    'mismatches':[p for p,h in m.items() if sha(ROOT/p)!=h]})
    assert not any(r['mismatches'] for r in records), 'Frozen artifact mismatch'
    return records

def verify_lock():
    lock=read(OUT/'E2_PROTOCOL_LOCK.json')
    assert lock['status']=='FROZEN'
    for p,h in lock['files'].items(): assert sha(ROOT/p)==h,p
    return lock
