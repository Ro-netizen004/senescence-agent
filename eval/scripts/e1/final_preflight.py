"""Outcome-free E1 validation; any failure prevents prospective lock."""
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
from execute_e1 import OUT,ROOT,ARGS,adapter,read_inputs,write,digest
from extract_panel import TARGETS
from agent.admissibility import check_admissibility
from tools.build_pseudobulk import build_pseudobulk_matrix
import pandas as pd

def main():
    destination=OUT/"final_preflight";destination.mkdir(exist_ok=False)
    tests=["eval/scripts/e1/test_prepare_e1.py","eval/scripts/e1/test_execution.py"]+[
        "backend/tests/"+name for name in ["test_admissibility_confounding.py","test_admissibility_replicates.py",
        "test_count_validation_and_covariates.py","test_replicate_stability.py","test_analysis_planner.py",
        "test_inference_state.py","test_output_firewall.py"]]
    run=subprocess.run([sys.executable,"-m","unittest","-v",*tests],capture_output=True,text=True)
    (destination/"tests.txt").write_text(run.stdout+run.stderr)
    if run.returncode:raise RuntimeError("Tests failed; see preserved log")
    checks={}
    with (destination/"adapters.log").open("x") as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        for target in TARGETS:
            c,m=read_inputs(target);data=adapter(c,m)
            gate=check_admissibility("run_deseq2",ARGS,data)
            rc,rm=build_pseudobulk_matrix(data,"CD4 T cell",group_column="perturbation",covariates=["donor_id"])
            pd.testing.assert_frame_equal(rc.loc[c.index,c.columns],c,check_dtype=False)
            if not gate["admissible"]:raise ValueError(f"Gate1 blocked {target}")
            checks[target]={"gate1":gate,"counts_exact":True,"n_pairs":m.donor_id.nunique(),
                            "actual_sample_cells":m.n_cells.to_dict()}
            del data
    source=json.loads((OUT/"sources/OFFICIAL_FULL_FILE_SHA256.json").read_text())
    if source["status"]!="VERIFIED" or source["bytes_read"]!=44566657140:raise ValueError("Source incomplete")
    if source["sha256"]!="fd2b8c21d357f8699ec34e2d5ebc1639612c27a0147a9ca94d4983822d93247e":
        raise ValueError("Source checksum mismatch")
    for p in (OUT/"data").iterdir():
        if p.is_file() and p.stat().st_mode&0o222:raise ValueError("Extracted source not read-only")
    freeze=subprocess.check_output([sys.executable,"-m","pip","freeze","--all"],text=True)
    if sorted(freeze.splitlines())!=sorted((ROOT/"TASK2_PIP_FREEZE.txt").read_text().splitlines()):
        raise ValueError("Frozen package mismatch")
    if subprocess.run([sys.executable,"-m","pip","check"],capture_output=True).returncode:raise ValueError("pip check failed")
    if sys.version.split()[0]!="3.11.9" or ".venv-task2" not in sys.executable:raise ValueError("Python mismatch")
    for name in ["AGENT_REPORT_MODEL","AGENT_REPORT_API_KEY","GEMINI_REPORT_MODEL","GEMINI_REPORT_API_KEY"]:
        if os.getenv(name):raise ValueError("Report override active")
    rubric=json.loads((OUT/"E1_CLAIM_CRITERIA_LOCK_MANIFEST.json").read_text())["files"][0]
    if digest(OUT/rubric["path"])!=rubric["sha256"]:raise ValueError("Rubric changed")
    if json.loads((OUT/"MODEL_ACCESS_PREFLIGHT.json").read_text())["status"]!="PASS":raise ValueError("Model access failed")
    write(destination/"PASS.json",{"status":"PASS","target_checks":checks,"new_de_fits":0,
          "scored_responses":0,"package_freeze_matches":True,"python":sys.version.split()[0],
          "tests_log_sha256":digest(destination/"tests.txt")})
    print("All final outcome-free preflights passed",flush=True)

if __name__=="__main__":main()
