"""Lock E1-S protocol/analysis before any saved-fit numerical comparisons."""
import json
import subprocess
import sys
from datetime import datetime,timezone
from common import ROOT,OUT,sha,write,original_check

def main():
    if (OUT/"SAVED_ANALYSIS_STARTED.json").exists():raise RuntimeError("Numerical analysis already started")
    if (OUT/"E1S_PROTOCOL_LOCK.json").exists():raise FileExistsError("Already locked")
    if not (OUT/"PHASE_A_COMPLETE.json").exists():raise RuntimeError("Phase A incomplete")
    result=subprocess.run([sys.executable,"-m","unittest","-v","eval/scripts/e1s/test_e1s.py"],capture_output=True,text=True)
    (OUT/"PRELOCK_TESTS.txt").write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError("Tests failed")
    checked=original_check()
    if checked["e1_mismatches"] or checked["prior_mismatches"]:raise ValueError("Source changed")
    paths=[p for p in OUT.rglob("*") if p.is_file()]+list((ROOT/"eval/scripts/e1s").glob("*.py"))+list((ROOT/"eval/scripts/e1s").glob("*.R"))
    write(OUT/"E1S_PROTOCOL_LOCK.json",{"timestamp_utc":datetime.now(timezone.utc).isoformat(),
         "status":"PROSPECTIVE_FOLLOWUP_TO_KNOWN_E1_LIMITATIONS","new_fits":0,"new_replies":0,
         "files":{str(p.relative_to(ROOT)):sha(p) for p in paths}})
    for p in paths:
        if OUT in p.parents:p.chmod(0o444)
    (OUT/"E1S_PROTOCOL_LOCK.json").chmod(0o444)
    print(json.dumps({"protocol_sha256":sha(OUT/"E1S_PROTOCOL.md"),"lock_sha256":sha(OUT/"E1S_PROTOCOL_LOCK.json")}))

if __name__=="__main__":main()
