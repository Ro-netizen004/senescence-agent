"""Staged E1 evaluation using unchanged agent planner, tool map and renderer.

The analysis stage never generates a governed report. Reporting is permitted
only after the independent opportunity table has been locked across all nine
targets. The adapter represents aggregated counts, not reconstructed cells.
"""
import argparse
import contextlib
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest.mock import patch
import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse
from statsmodels.stats.multitest import multipletests

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"eval/results/v2/e1/e1_v2_1_20261022_01"
sys.path.insert(0,str(ROOT/"backend"))
from extract_panel import TARGETS

ARGS=dict(cell_type="CD4 T cell",sample_column="sample_id",group_column="perturbation",
          reference_group="NTC",comparison_group="targeting",covariates=["donor_id"])
PROMPT=("Run donor-paired pseudobulk DESeq2 for {target} CRISPRi versus non-targeting controls "
        "in primary human CD4 T cells under Stim8hr. Use raw summed UMI counts; donor_id is "
        "the biological unit and pairing covariate. Use sample_id for donor-by-arm samples, "
        "perturbation as grouping variable, NTC as reference and targeting as comparison. "
        "Do not change this design or infer independent replication from guides or cells. "
        "Address on-target expression, supported downstream RNA changes, donor limitations "
        "and unsupported protein or mechanistic interpretations. No external validation "
        "outcomes or evaluator labels are supplied.")

def digest(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def safe(value):
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe(v) for v in value]
    if isinstance(value,np.generic):return safe(value.item())
    if isinstance(value,float) and not np.isfinite(value):return None
    return value

def write(path,value):
    with Path(path).open("x") as f:
        json.dump(safe(value),f,indent=2,allow_nan=False);f.write("\n")

def verify_lock():
    lock=json.loads((OUT/"E1_PROTOCOL_LOCK_MANIFEST.json").read_text())
    for relative,expected in lock["files"].items():
        if digest(ROOT/relative)!=expected:raise ValueError("Frozen input mismatch: "+relative)
    if os.getenv("GEMINI_MODEL")!="gemini-3.5-flash":raise ValueError("Model mismatch")
    if os.getenv("AGENT_GOVERNANCE","").lower() in ["off","0","false"]:raise ValueError("Governance disabled")
    return lock

def adapter(counts,meta):
    """Lossless raw-sum transport with the *verified actual* cell count per arm.

    One transport row carries the sum; the rest are zero. These are not inferred
    single-cell profiles and must never feed cell-level analyses or QC.
    """
    blocks=[];rows=[]
    for sample in counts.index:
        m=meta.loc[sample]; n=int(m.n_cells)
        if n<20:raise ValueError("Actual cell count below unchanged Gate1 minimum")
        blocks.append(sparse.vstack([sparse.csr_matrix(counts.loc[[sample]].to_numpy(dtype=np.int64)),
                                    sparse.csr_matrix((n-1,counts.shape[1]),dtype=np.int64)],format="csr"))
        rows.append(pd.DataFrame({"sample_id":sample,"donor_id":str(m.donor_id),
                                  "perturbation":str(m.perturbation),"cell_type":"CD4 T cell"},
                                 index=[f"{sample}__transport_{i}" for i in range(n)]))
    matrix=sparse.vstack(blocks,format="csr")
    data=ad.AnnData(X=matrix,obs=pd.concat(rows),var=pd.DataFrame(index=counts.columns.astype(str)))
    data.layers["counts"]=matrix.copy()
    data.uns["dataset_profile"]={"sample_column":"sample_id","cell_type_column":"cell_type",
        "primary_group_column":"perturbation","group_columns":[{"column":"perturbation","values":["NTC","targeting"]}],
        "deseq2_covariates":["donor_id"]}
    data.uns["evaluation_adapter"]={"not_single_cell_data":True,"verified_actual_cell_counts":True}
    return data

def read_inputs(target):
    p=OUT/"prepared"/target
    return pd.read_csv(p/"counts.csv.gz",index_col=0),pd.read_csv(p/"metadata.csv",index_col=0)

def independent_supported(frame,qcolumn):
    finite=np.isfinite(frame[["log2FoldChange","lfcSE",qcolumn]]).all(axis=1)
    return (finite & frame.lfcSE.ge(0) & frame[qcolumn].lt(.05)
            & (frame.log2FoldChange.abs()>1.959963984540054*frame.lfcSE))

def paired_omission_masks(meta):
    return {str(d):~meta.donor_id.eq(d) for d in sorted(meta.donor_id.unique())}

def analyze():
    verify_lock()
    root=OUT/"execution"
    root.mkdir(exist_ok=False)
    from agent.admissibility import check_admissibility
    from agent.intent_router import RouteDecision
    from agent.analysis_planner import plan_route
    from agent.tool_router import build_tool_map
    from tools.build_pseudobulk import build_pseudobulk_matrix
    from tools.run_deseq2 import run_deseq2_pseudobulk
    import tools.config as config
    from google import genai
    from google.genai import types
    real_client=genai.Client
    statuses=[]
    for target in TARGETS:
        p=root/target;p.mkdir()
        status={"target":target,"status":"STARTED","primary_deseq2_calls":0,"sensitivity_calls":0,
                "gemini_calls":0,"retries":0,"started_at":datetime.now(timezone.utc).isoformat()}
        write(p/"ATTEMPT.json",status)
        try:
            counts,meta=read_inputs(target)
            data=adapter(counts,meta)
            gate=check_admissibility("run_deseq2",ARGS,data);write(p/"gate1.json",gate)
            if not gate["admissible"]:raise ValueError("Gate1 rejected")
            rebuilt,rm=build_pseudobulk_matrix(data,"CD4 T cell",group_column="perturbation",covariates=["donor_id"])
            pd.testing.assert_frame_equal(rebuilt.loc[counts.index,counts.columns],counts,check_dtype=False)
            if not (rm.loc[meta.index,"donor_id"].astype(str)==meta.donor_id.astype(str)).all():
                raise ValueError("Adapter donor mismatch")
            write(p/"adapter_verification.json",{"counts_exact":True,"actual_cell_counts":meta.n_cells.to_dict(),
                  "not_single_cell_profiles":True,"only_pseudobulk_path_permitted":True})
            prompt=PROMPT.format(target=target)
            (p/"prompt.txt").write_text(prompt+"\n")
            decision=RouteDecision(workflow_id="deseq2",tool_args={"run_deseq2":ARGS.copy()})
            def no_retry_client(*args,**kwargs):
                kwargs["http_options"]=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1))
                return real_client(*args,**kwargs)
            with patch("agent.analysis_planner.genai.Client",side_effect=no_retry_client):
                status["gemini_calls"]=1
                planned,audit=plan_route(prompt,data,decision)
            if audit.get("status")=="deterministic_fallback":
                # Do not persist raw API exception text, which can contain credentials.
                write(p/"planner_failure.json",{"status":"API_OR_EMPTY_PLANNER_FAILURE","fallback_used":False})
                raise RuntimeError("Planner unavailable; deterministic fallback prohibited")
            write(p/"gemini_plan.json",audit)
            if planned.tool_args["run_deseq2"]!=ARGS:raise ValueError("Planner changed frozen arguments")
            config.OUTPUT_DIR=str(p)
            toolmap=build_tool_map(data,"human",{},governed=True)
            with (p/"analysis.log").open("x") as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                status["primary_deseq2_calls"]=1
                result=toolmap["run_deseq2"](ARGS.copy())
            write(p/"tool_result.json",result)
            if result.get("covariates_used")!=["donor_id"] or result.get("covariates_dropped"):
                raise ValueError("Unexpected design")
            if not (p/"deseq2_results.csv").exists():raise ValueError("Full result export missing")
            write(p/"gene_filter.json",{"total_genes":len(counts.columns),"kept":int((counts.sum()>=10).sum()),
                                         "rule":"total raw counts >= 10; recomputed per fit"})
            if meta.donor_id.nunique()==4:
                sensitivity=p/"paired_sensitivity";sensitivity.mkdir()
                for donor,keep in paired_omission_masks(meta).items():
                    with (sensitivity/f"{donor}.log").open("x") as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                        status["sensitivity_calls"]+=1
                        fitted=run_deseq2_pseudobulk(counts.loc[keep],meta.loc[keep],group_column="perturbation",
                                    reference_group="NTC",comparison_group="targeting",covariates=["donor_id"])
                    fitted["results"].to_csv(sensitivity/f"{donor}.csv")
            status["status"]="ANALYSIS_COMPLETE_REPORT_PENDING"
        except Exception as exc:
            status.update(status="EXECUTION_FAIL",error_type=type(exc).__name__)
            # Error details from non-API scientific fits remain in analysis logs.
        status["finished_at"]=datetime.now(timezone.utc).isoformat()
        write(p/"STATUS.json",status);statuses.append(status)
        print(json.dumps(status),flush=True)
        if status["status"]=="EXECUTION_FAIL":
            # Preserve all downstream cases as unattempted; no automatic retry.
            break
    for target in TARGETS[len(statuses):]:
        statuses.append({"target":target,"status":"NOT_ATTEMPTED_AFTER_FAILURE"})
    write(root/"CASE_STATUS.json",statuses)

def opportunities():
    """Only independent statistics/metadata enter; no tool_result or Gate2 read."""
    verify_lock()
    case_status=json.loads((OUT/"execution/CASE_STATUS.json").read_text())
    raw=[];frames={};testable={}
    target_ids=pd.read_csv(OUT/"E1_TARGET_ELIGIBILITY.csv").set_index("target").target_gene_id.to_dict()
    for s in case_status:
        t=s["target"];p=OUT/"execution"/t/"deseq2_results.csv"
        valid=s["status"]=="ANALYSIS_COMPLETE_REPORT_PENDING" and p.exists()
        if valid:
            df=pd.read_csv(p,index_col=0);frames[t]=df
            valid=target_ids[t] in df.index and np.isfinite(df.loc[target_ids[t],"pvalue"])
        testable[t]=bool(valid)
        raw.append(float(frames[t].loc[target_ids[t],"pvalue"]) if valid else 1.)
    qs=multipletests(raw,method="fdr_bh")[1]
    selected=[];on_target=[]
    for i,t in enumerate(TARGETS):
        on_target.append({"target":t,"testable":testable[t],"correction_input_p":raw[i],"family_a_q":float(qs[i])})
        if t not in frames:continue
        df=frames[t];supported=df.loc[independent_supported(df,"padj")].copy()
        supported["gene_id"]=supported.index.astype(str)
        downstream=supported.loc[supported.index!=target_ids[t]].sort_values(["padj","gene_id"]).head(10)
        candidates=[(g,r,"B",r.padj) for g,r in downstream.iterrows()]
        if testable[t]:
            one=df.loc[[target_ids[t]]].assign(family_a_q=qs[i])
            if independent_supported(one,"family_a_q").iloc[0]:
                candidates.insert(0,(target_ids[t],one.iloc[0],"A",qs[i]))
        for g,r,family,q in candidates:
            sensitivity=[]
            for file in sorted((OUT/"execution"/t/"paired_sensitivity").glob("*.csv")):
                small=pd.read_csv(file,index_col=0)
                sensitivity.append(float(small.loc[g,"log2FoldChange"]) if g in small.index else np.nan)
            robust=(len(sensitivity)==4 and all(np.isfinite(v) and np.sign(v)==np.sign(r.log2FoldChange)
                         and abs(v)>=.5*abs(r.log2FoldChange) for v in sensitivity))
            selected.append({"id":f"{t}:{g}:{family}","target":t,"gene_id":str(g),"family":family,
                "log2FoldChange":float(r.log2FoldChange),"lfcSE":float(r.lfcSE),"q":float(q),
                "direction":"increased" if r.log2FoldChange>0 else "decreased",
                "paired_robustness_supported":robust,"paired_sensitivity_available":len(sensitivity)==4,
                "required_scope":"RNA in Stim8hr primary human CD4 T cells; limited donor replication; no mechanism/protein inference"})
    write(OUT/"E1_SUPPORTED_CLAIM_OPPORTUNITIES.json",selected)
    write(OUT/"E1_ON_TARGET_FAMILY_A.json",on_target)
    write(OUT/"OPPORTUNITY_LOCK.json",{"timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "gate2_consulted":False,"responses_generated":0,"files":{
            name:digest(OUT/name) for name in ["E1_SUPPORTED_CLAIM_OPPORTUNITIES.json","E1_ON_TARGET_FAMILY_A.json"]}})

def report():
    verify_lock()
    lock=json.loads((OUT/"OPPORTUNITY_LOCK.json").read_text())
    for name,h in lock["files"].items():
        if digest(OUT/name)!=h:raise ValueError("Opportunity lock mismatch")
    from agent.inference_state import apply_inference_state
    from agent.output_renderer import render_tool_calls_with_schema
    for status in json.loads((OUT/"execution/CASE_STATUS.json").read_text()):
        if status["status"]!="ANALYSIS_COMPLETE_REPORT_PENDING":continue
        p=OUT/"execution"/status["target"]
        tool=json.loads((p/"tool_result.json").read_text())
        # Evaluation packet exposes all production statistics (the normal UI
        # truncates to 100), without selecting rows using evaluator opportunities.
        # No gate decision, effect estimate or p-value is changed.
        full=pd.read_csv(p/"deseq2_results.csv",index_col=0)
        tool["results"]=safe(full.rename_axis("gene").reset_index().to_dict(orient="records"))
        family_a=json.loads((OUT/"E1_ON_TARGET_FAMILY_A.json").read_text())
        tool["family_a_statistics"]=[r for r in family_a if r["target"]==status["target"]]
        packet={"target":status["target"],"prompt":PROMPT.format(target=status["target"]),
                "tool_payload":tool,"full_results_file":"deseq2_results.csv",
                "external_reference_outcomes_supplied":False}
        write(p/"canonical_evidence_packet.json",packet)
        governed=apply_inference_state("run_deseq2",tool,ARGS.copy())
        reply,schemas=render_tool_calls_with_schema([{"name":"run_deseq2","args":ARGS.copy(),"result":governed}])
        write(p/"governed_result.json",governed);write(p/"output_schema.json",schemas)
        with (p/"original_governed_reply.txt").open("x") as f:f.write(reply)
        write(p/"REPORT_STATUS.json",{"status":"COMPLETE","reporter":"unchanged deterministic governed renderer",
              "new_gemini_report_calls":0,"opportunity_lock_sha256":digest(OUT/"OPPORTUNITY_LOCK.json")})

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("stage",choices=["analyze","opportunities","report"])
    {"analyze":analyze,"opportunities":opportunities,"report":report}[parser.parse_args().stage]()
