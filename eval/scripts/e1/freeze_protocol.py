"""Prospective one-way E1 input lock. Never run after an execution directory exists."""
import json
import subprocess
from datetime import datetime,timezone
from execute_e1 import ROOT,OUT,digest,write

def main():
    if (OUT/"execution").exists():raise RuntimeError("Cannot preregister after execution")
    if not (OUT/"final_preflight/PASS.json").exists():raise RuntimeError("Missing preflight")
    if (OUT/"E1_PROTOCOL_LOCK_MANIFEST.json").exists():raise FileExistsError("Protocol already frozen")
    candidates=[p for p in OUT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    candidates += list((ROOT/"eval/scripts/e1").glob("*.py"))
    candidates += list((ROOT/"backend").rglob("*.py"))
    candidates += [ROOT/"TASK2_PIP_FREEZE.txt"]
    candidates=[p for p in candidates if p.name not in {"REPOSITORY_AUDIT.json","FROZEN_FINAL_VERIFICATION.json"}]
    record={"status":"FROZEN_BEFORE_E1_SCIENTIFIC_EXECUTION",
            "timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "git_revision":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
            "e1_primary_fits":0,"e1_sensitivity_fits":0,"e1_generated_reports":0,"e1_scored_reports":0,
            "published_reference_outcomes_inspected":True,
            "files":{str(p.relative_to(ROOT)):digest(p) for p in sorted(set(candidates))}}
    write(OUT/"E1_PROTOCOL_LOCK_MANIFEST.json",record)
    for p in candidates:
        if OUT in p.parents:p.chmod(0o444)
    (OUT/"E1_PROTOCOL_LOCK_MANIFEST.json").chmod(0o444)
    print(json.dumps({"status":record["status"],"timestamp_utc":record["timestamp_utc"],
          "locked_files":len(record["files"]),"protocol_sha256":digest(OUT/"E1_PROTOCOL_V2_1.md"),
          "manifest_sha256":digest(OUT/"E1_PROTOCOL_LOCK_MANIFEST.json")}))

if __name__=="__main__":main()
