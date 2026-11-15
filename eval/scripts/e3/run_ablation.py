#!/usr/bin/env python3
"""Offline E3 architecture counterfactual; calls the unchanged production gates."""
from __future__ import annotations
import csv, hashlib, json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
OUTPUT = REPO / "eval/results/v2/e3/code_reproduction"
sys.path.insert(0, str(REPO / "backend"))
from agent.admissibility import check_admissibility
from agent.inference_state import apply_inference_state

class Raw:
    def __init__(self, X, var_names): self.X, self.var_names = X, var_names
class FakeAnnData:
    """Small synthetic adapter implementing only the fields production checks read."""
    def __init__(self, X, obs, uns=None, layers=None, var_names=None):
        self.X = np.asarray(X); self.obs = obs.reset_index(drop=True); self.uns = uns or {}
        self.layers = layers or {}; self.var_names = list(var_names or [f"g{i}" for i in range(self.X.shape[1])]); self.raw = None
    def __getitem__(self, mask):
        mask = np.asarray(mask)
        out = FakeAnnData(self.X[mask], self.obs.loc[mask].reset_index(drop=True), dict(self.uns),
                          {k: np.asarray(v)[mask] for k,v in self.layers.items()}, self.var_names)
        out.raw = self.raw
        return out

def fixture(case):
    design = case["design"]
    n_per = 2 if design == "two_replicates" else 3
    has_sample = design != "no_replicate_unit"
    rows=[]; mat=[]
    groups=["control","treated"]
    for gi,g in enumerate(groups):
        for si in range(n_per):
            sid=f"{g}_{si}"
            batch = g if design == "perfect_confounding" else ("b1" if si % 2 == 0 else "b2")
            for c in range(20):
                row={"condition":g,"cell_type":"fibroblast","batch":batch}
                if has_sample: row["sample_id"]=sid
                rows.append(row)
                vals=[10,20,30]
                if case["result"] == "positive_stable": vals[0] = 80 if gi else 10
                mat.append(vals)
    X=np.asarray(mat,dtype=float)
    raw_layer=X.copy()
    if design == "invalid_counts": raw_layer=raw_layer + 0.5
    obs=pd.DataFrame(rows)
    ad=FakeAnnData(X,obs,uns={"dataset_profile":{"sample_column":"sample_id","primary_group_column":"condition","cell_type_column":"cell_type"}},layers={"counts":raw_layer},var_names=["senescence_marker","gene_b","gene_c"])
    args={"sample_column":"sample_id","group_column":"condition","reference_group":"control","comparison_group":"treated","cell_type_column":"cell_type"}
    return ad,args

def result_record(case):
    result={"samples_per_group":{"control":3,"treated":3},"n_significant_fdr_0_05":1,"results":[],"warnings":[]}
    if case["result"] == "nonsignificant": result["n_significant_fdr_0_05"]=0
    if case["result"] == "artifact_suspect": result["result_plausibility"]={"verdict":"suspect"}
    if case["result"] == "unstable": result["replicate_stability"]={"verdict":"unstable"}
    if case["result"] == "stability_unestablished": result["replicate_stability"]={"verdict":"assessment_failed"}
    return result

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    registry=json.loads((ROOT/"cases.json").read_text())
    OUTPUT.mkdir(parents=True, exist_ok=False)
    rows=[]
    for case in registry["cases"]:
        ad,args=fixture(case)
        try:
            g1=check_admissibility("run_deseq2",args,ad)
            g1_error=None
        except Exception as e:
            g1={"admissible":None,"blocked_reasons":[],"checks":{}}
            g1_error=f"{type(e).__name__}: {e}"
        result=result_record(case)
        try:
            g2=apply_inference_state("run_deseq2",result,args).get("inference_state",{})
            g2_error=None
        except Exception as e:
            g2={"state":"ERROR","allowed_interpretation_level":"ERROR","validity_flags":[]}
            g2_error=f"{type(e).__name__}: {e}"
        gate1_block = g1.get("admissible") is False
        g2_licensed = g2.get("allowed_interpretation_level")=="INFERENTIAL"
        ungated_licensed = case["result"] != "nonsignificant"
        expected_valid=case["class"].startswith("valid_")
        expected_claim=case["claim"]
        arms={
          "full_firewall": (gate1_block, False if gate1_block else g2_licensed),
          "gate1_only": (gate1_block, False if gate1_block else ungated_licensed),
          "gate2_only": (False, g2_licensed),
          "neither": (False, ungated_licensed),
        }
        for arm,(blocked,licensed) in arms.items():
            accepted = (not licensed) if case["class"].startswith("invalid_") else (licensed if case["class"]=="valid_positive" else not licensed)
            if case["class"]=="valid_nonsignificant": accepted = (g2.get("state")=="NOT_SIGNIFICANT") if arm in ("full_firewall","gate2_only") else True
            claim_preserved = (licensed if expected_claim=="qualified_expression_association" else (not licensed if expected_claim=="qualified_nonsignificance" else False))
            # A design block counts as rejection even if a local Gate 2-only result would license it.
            rows.append({"case_id":case["id"],"reference_class":case["class"],"design":case["design"],"result":case["result"],"arm":arm,"gate1_admissible":g1.get("admissible"),"gate1_blocked":gate1_block,"gate1_reasons":g1.get("blocked_reasons",[]),"gate2_state":g2.get("state"),"gate2_interpretation":g2.get("allowed_interpretation_level"),"gate2_validity_flags":g2.get("validity_flags",[]),"inference_licensed":licensed,"valid_case_acceptance_correct":bool(expected_valid and accepted),"invalid_case_rejection_correct":bool((not expected_valid) and accepted),"supported_claim_preserved":bool(expected_valid and claim_preserved),"gate1_error":g1_error,"gate2_error":g2_error})
    out=OUTPUT/"per_case_scores.json"
    out.write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    csv_path=OUTPUT/"per_case_scores.csv"
    with csv_path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for row in rows:
            w.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    summary=[]
    for arm in ("full_firewall","gate1_only","gate2_only","neither"):
        ar=[r for r in rows if r["arm"]==arm]
        summary.append({"arm":arm,"valid_case_acceptance_correct":sum(r["valid_case_acceptance_correct"] for r in ar if r["reference_class"].startswith("valid_")),"valid_case_denominator":12,"invalid_case_rejection_correct":sum(r["invalid_case_rejection_correct"] for r in ar if r["reference_class"].startswith("invalid_")),"invalid_case_denominator":12,"supported_claims_preserved":sum(r["supported_claim_preserved"] for r in ar),"supported_claim_denominator":12,"inferentially_licensed_valid_positive":sum(r["inference_licensed"] for r in ar if r["reference_class"]=="valid_positive"),"inferentially_licensed_invalid":sum(r["inference_licensed"] for r in ar if r["reference_class"].startswith("invalid_")),"case_count":len(ar),"errors":sum(bool(r["gate1_error"] or r["gate2_error"]) for r in ar)})
    (OUTPUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    with (OUTPUT/"summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
