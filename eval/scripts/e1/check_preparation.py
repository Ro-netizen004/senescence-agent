"""Record non-scientific E1 preparation checks; never call a model or fit DE."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "eval/results/v2/e1/e1_v2_1_20261022_01"

def main():
    lock=json.loads((OUT/"E1_CLAIM_CRITERIA_LOCK_MANIFEST.json").read_text())
    rubric=lock["files"][0]
    rubric_ok=hashlib.sha256((OUT/rubric["path"]).read_bytes()).hexdigest()==rubric["sha256"]
    environment=dict(os.environ)
    environment["PYTHONPATH"]=str(ROOT/"eval/scripts/e1")+os.pathsep+str(ROOT/"backend")
    tests=subprocess.run([sys.executable,"-m","unittest","-v","eval/scripts/e1/test_prepare_e1.py"],
                         cwd=ROOT,env=environment,capture_output=True,text=True)
    log=OUT/"PREPARATION_TESTS.txt"
    with log.open("x") as handle:
        handle.write(tests.stdout+tests.stderr)
    packages=subprocess.run([sys.executable,"-m","pip","check"],capture_output=True,text=True)
    freeze=subprocess.run([sys.executable,"-m","pip","freeze","--all"],capture_output=True,text=True)
    expected=(ROOT/"TASK2_PIP_FREEZE.txt").read_text()
    freeze_matches=sorted(freeze.stdout.splitlines())==sorted(expected.splitlines())
    frozen=json.loads((OUT/"FROZEN_FINAL_VERIFICATION.json").read_text())
    prepared={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((OUT/"prepared").rglob("*")) if p.is_file()}
    result={"timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "scope":"preparation only; not scientific execution authorization",
            "rubric_hash_matches_lock":rubric_ok,"preparation_tests_exit_code":tests.returncode,
            "python_version":sys.version.split()[0],"python_executable":sys.executable,
            "pip_check_exit_code":packages.returncode,"pip_check_output":packages.stdout+packages.stderr,
            "task2_freeze_all_matches":freeze_matches,"frozen_baseline_check":frozen,
            "prepared_file_hashes":prepared,"e1_de_calls":0,"e1_generated_responses":0,
            "e1_scored_responses":0,"execution_protocol_frozen":False}
    with (OUT/"PREPARATION_CHECKS.json").open("x") as handle:
        json.dump(result,handle,indent=2)
        handle.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k!="prepared_file_hashes"},indent=2))
    if not rubric_ok or tests.returncode or packages.returncode or frozen["differences"]:
        raise SystemExit(1)

if __name__=="__main__":
    main()
