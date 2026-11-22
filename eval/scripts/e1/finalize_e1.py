"""Preserve E1 completion accounting, limitations and final manifest; no analysis rerun."""
import json
import re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import subprocess
import sys
import numpy as np
import pandas as pd
from execute_e1 import OUT,ROOT,write,digest,verify_lock

def main():
    verify_lock()
    if (OUT/"E1_SUMMARY_METRICS.json").exists():raise FileExistsError("Already finalized")
    audit=subprocess.run([sys.executable,str(ROOT/"eval/scripts/e1/audit_frozen.py")],capture_output=True,text=True)
    if audit.returncode:raise RuntimeError("Frozen preservation audit failed")
    baseline=json.loads((OUT/"FROZEN_FINAL_VERIFICATION.json").read_text())
    if baseline["differences"]:raise ValueError("Frozen historical artifacts changed")
    statuses=json.loads((OUT/"execution/CASE_STATUS.json").read_text())
    communication=json.loads((OUT/"E1_COMMUNICATION_METRICS.json").read_text())
    eligible=pd.read_csv(OUT/"E1_TARGET_ELIGIBILITY.csv").set_index("target")
    family={r["target"]:r for r in json.loads((OUT/"E1_ON_TARGET_FAMILY_A.json").read_text())}
    opportunities=json.loads((OUT/"E1_SUPPORTED_CLAIM_OPPORTUNITIES.json").read_text())
    concordance=pd.read_csv(OUT/"E1_BIOLOGICAL_CONCORDANCE.csv")
    warning_rows=[];targets=[];native_checks=[]
    for status in statuses:
        t=status["target"];p=OUT/"execution"/t
        if not (p/"deseq2_results.csv").exists():continue
        df=pd.read_csv(p/"deseq2_results.csv",index_col=0)
        row=df.loc[eligible.loc[t,"target_gene_id"]]
        tool=json.loads((p/"tool_result.json").read_text())
        state=json.loads((p/"output_schema.json").read_text())[0]["inference_state"]
        plan=json.loads((p/"gemini_plan.json").read_text())
        targets.append({"target":t,"execution_status":status["status"],"report_status":"COMPLETE",
            "donor_pairs":int(eligible.loc[t,"complete_donor_pairs"]),"on_target_log2FC":float(row.log2FoldChange),
            "on_target_lfcSE":float(row.lfcSE),"on_target_family_A_q":family[t]["family_a_q"],
            "on_target_direction":"decreased" if row.log2FoldChange<0 else "increased",
            "downstream_fdr_count":int(df.padj.lt(.05).sum()),"gate1":"ADMISSIBLE",
            "native_plausibility":tool["result_plausibility"]["verdict"],
            "native_stability":tool["replicate_stability"]["verdict"],"inference_state":state,
            "planner_status":plan["status"],"independent_opportunities":sum(r["target"]==t for r in opportunities),
            "paired_robust_opportunities":sum(r["target"]==t and r["paired_robustness_supported"] for r in opportunities)})
        for f in p.rglob("*.log"):
            for line_number,line in enumerate(f.read_text().splitlines(),1):
                if "Warning:" in line:
                    warning_rows.append({"target":t,"file":str(f.relative_to(OUT)),"line":line_number,
                                         "exact_warning":line,"message":line.split("Warning:",1)[1].strip()})
        # Independently reconstruct the *native* single-sample omission metric.
        # This is separate verification, never opportunity creation.
        c=pd.read_csv(OUT/"prepared"/t/"counts.csv.gz",index_col=0)
        m=pd.read_csv(OUT/"prepared"/t/"metadata.csv",index_col=0)
        genes=df.index[df.padj.fillna(1).lt(.05)]
        if m.donor_id.nunique()==4 and len(genes):
            normalized=np.log2(c.loc[:,genes].div(c.sum(axis=1),axis=0)*1e6+1)
            effect=normalized[m.perturbation.eq("targeting")].mean()-normalized[m.perturbation.eq("NTC")].mean()
            omitted=[]
            for sample in m.index:
                keep=m.index!=sample
                z=normalized.loc[keep];groups=m.loc[keep,"perturbation"]
                omitted.append(z[groups.eq("targeting")].mean()-z[groups.eq("NTC")].mean())
            omissions=pd.DataFrame(omitted)
            stable=(np.sign(omissions).eq(np.sign(effect)).all() & effect.ne(0)
                    & omissions.abs().min().div(effect.abs().replace(0,np.nan)).fillna(0).ge(.5))
            native_checks.append({"target":t,"single_sample_omission_stable_count_matches":
                                  int(stable.sum())==tool["replicate_stability"]["n_stable_genes"],
                                  "not_paired_donor_refits":True})
    write(OUT/"E1_NATIVE_GATE_VERIFICATION.json",native_checks)
    pd.DataFrame(warning_rows).to_csv(OUT/"E1_NUMERICAL_WARNINGS.csv",index=False)
    warning_counts=Counter(r["message"] for r in warning_rows)
    counts={"primary_deseq2":sum(r.get("primary_deseq2_calls",0) for r in statuses),
            "paired_sensitivity_deseq2":sum(r.get("sensitivity_calls",0) for r in statuses),
            "gemini_planner":sum(r.get("gemini_calls",0) for r in statuses),"non_scientific_model_access":1,
            "gemini_reporter":0,"retries":sum(r.get("retries",0) for r in statuses)}
    summary={"status":"PARTIAL_SCIENTIFIC_VALIDATION_WITH_COMPLETE_REGISTERED_EXECUTION",
        "finished_at_utc":datetime.now(timezone.utc).isoformat(),"targets_intended":9,"targets_eligible":9,
        "targets_analyzed":len(targets),"responses_preserved":communication["completed_responses"],
        "execution_api_failures":[],"call_counts":counts,"per_target":targets,
        "on_target_family_A_significant_decreases":sum(r["on_target_family_A_q"]<.05 and r["on_target_log2FC"]<0 for r in targets),
        "rna_direction_agreement":{"agree":int(concordance.loc[concordance.assay.eq("arrayed_bulk_RNA"),"direction_agreement"].sum()),"denominator":27,"qualified_not_exact_replication":True},
        "protein_direction_agreement":{"agree":int(concordance.loc[concordance.assay.eq("intracellular_flow"),"direction_agreement"].sum()),"denominator":12,"contextual_only_condition_mismatch":True},
        "communication":communication,"numerical_warning_counts":dict(warning_counts),
        "frozen_baseline_verification":baseline,"protocol_sha256":digest(OUT/"E1_PROTOCOL_V2_1.md"),
        "protocol_lock_sha256":digest(OUT/"E1_PROTOCOL_LOCK_MANIFEST.json"),
        "remaining_validation_limits":["Nine on-target communication scores unresolved due to reporter identity mapping omission",
            "Exact bulk-validation donor membership unverified; protein condition mismatch",
            "Low residual degrees of freedom, arithmetic warnings and dispersion fallback; arithmetic agreement does not certify fit adequacy",
            "Internal semantic inventory is provisional and non-exhaustive; no independent human biological adjudication"],
        "E2_E3_E4_started":False,"scientific_rerun_permitted_by_this_report":False}
    write(OUT/"E1_SUMMARY_METRICS.json",summary)
    table="\n".join(f"| {r['target']} | {r['donor_pairs']} | {r['on_target_log2FC']:.3f} | {r['on_target_family_A_q']:.3g} | {r['downstream_fdr_count']} | {r['native_plausibility']} / {r['native_stability']} |" for r in targets)
    text=f"""# E1 biological validation — final registered-attempt report

Status: **PARTIAL scientific validation; registered execution and reporting complete.**
All nine primary analyses, 24 prespecified paired-donor sensitivity fits and
nine original governed replies are preserved. No execution/API failure or
retry occurred. No E2–E4 experiment was started. Do not rerun this attempt.

## Prospective controls and provenance

The independent rubric and execution protocol were locked before new E1 fits
and scored replies. Protocol SHA-256:
`{summary['protocol_sha256']}`.
Lock SHA-256: `{summary['protocol_lock_sha256']}`.
Official source SHA-256:
`fd2b8c21d357f8699ec34e2d5ebc1639612c27a0147a9ca94d4983822d93247e`
(44,566,657,140 bytes, full stream verified; read-only extracted subset).
Published external outcomes were inspected before the execution lock and are
disclosed. The 99-opportunity table was hashed after analysis but before any
governed reply. No Gate 2 output was used to create opportunities.

Fifty-five preparation/runner/targeted tests passed before execution; three
additional scoring-arithmetic tests passed after execution. Their implementation
timing is disclosed; the rubric was not changed. All 691 baseline-snapshotted
frozen artifact/protocol/production-code files remain unchanged. Pre-existing
historical final_candidate manifest discrepancies remain untouched.

## Statistical results and gates

Raw donor-level sums, complete paired samples and full-rank donor + perturbation
models were used. Cells and guides were not independent replicates. Six targets
had four pairs; CYB5R4, ELOB and MEN1 had three. Minimum actual cells per arm was
20; minimum guide cells five; source condition-count quantile 5,332.66 UMIs;
gene-total filter >=10. No efficacy filter or outcome-based case selection.

| Target | Donor pairs | On-target log2FC | Nine-test BH q | Genes at within-contrast FDR<.05 | Native plausibility / stability |
|---|---:|---:|---:|---:|---|
{table}

All nine on-target effects are decreases under the registered statistical rule.
This is not proof that all downstream effects are genuine biological effects.
Six governed reports withheld gene-level results. KDM1A, MED24 and SGF29 displayed
numerical results. Native Gate 2 is unchanged and uses single-sample log-CPM
omissions, not paired-donor refits. Independent four-donor sensitivities are
separately preserved and never substituted into Gate 2.

## Independent references

RNA directions agree in 22/27 fixed target/outcome comparisons. Exact bulk
donor membership is unverified; the author guide-aware donor+PC1 model differs
from this donor-collapsed analysis. Protein directions agree in 11/12 associations,
but those six-hour cocktail/Brefeldin measurements are contextual, not directly
matched eight-hour RNA validation. Every agreement and disagreement is in
`E1_BIOLOGICAL_CONCORDANCE.csv`. These descriptive ratios are not accuracy scores.

NFKB2–IL10: E1 RNA log2FC -3.085 (within-contrast q=0.006925), external arrayed
RNA -1.992 (q≈0.000024), protein percent-positive log2 ratio +0.816 (q≈0.280).
The nonsignificant, different-condition protein result does not establish no
protein effect. KDM1A's two guide-design records flag a possible bidirectional
promoter involving TEX46; this is a limitation, not demonstrated off-target action.

## Communication assessment — provisional and incomplete

The frozen rule yields 99 intended opportunities: nine on-target and 90 downstream.
Six blanket withholding replies explicitly refuse 60 downstream opportunities
supported by the independent statistical rule. Three replies communicate the
30 selected downstream numerical effects, but omit required limited-donor
qualification; numerical mention is not full qualified retention. Nine on-target
communication judgments are UNRESOLVED_INPUT_ACCESS: actual packets omitted an
explicit target-symbol/Ensembl mapping. Packets and replies were not repaired
retroactively. The intended denominator remains 99, not a selectively reduced 90.

Conditional internal tallies: fully retained 0/99; explicit refusals 60/99;
qualification omissions 30/99; unresolved 9/99. Both completed-response and
intention-to-report retention are 0/99 because all nine replies completed.
These are conditional rubric judgments, **not proof that 60 true biological
findings were wrongly refused**. The evidence-access defect and numerical
limitations prevent a definitive biological false-refusal rate.

The adjudicated atomic inventory contains three unsupported universal statistical
necessity statements (requiring stability for any inference) and three unresolved
artifact-versus-biology statements with mixed hedging. No positive mechanism or
protein extrapolation was identified in these deterministic replies. Advice and
generic policy text were not exhaustively independently adjudicated; consequently
the exhaustive semantic unsupported-claim rate remains undefined, not zero.
All exact spans and reasons are saved. This is internal assessment, not E4 or
independent human validation. Scoring code was written after replies under the
already frozen criteria; it is not represented as a preregistered implementation.

## Numerical warnings and verification limits

Across 33 fits: 33 residual-degree-of-freedom warnings, 25 mean-dispersion trend
fallback warnings, and 261 occurrences each of divide-by-zero, overflow and
invalid-value matrix-multiplication warnings. Exact original messages and file/
line locators are preserved in `E1_NUMERICAL_WARNINGS.csv`; full logs remain.
The installed warning condition is residual df <=3 although its message says
less than 3. Primary paired designs have residual df 3 or 2; omission fits have 2.

All nine saved Wald statistics agree with log2FC/SE, two-sided normal p-values
agree, finite-family BH adjustments agree, and the nine-test on-target correction
agrees with independent arithmetic. Native single-sample stability counts were
also independently reproduced. These checks support output consistency, **not**
proof of optimization adequacy, dispersion calibration or absence of systematic
library-size effects. Internal optimizer states were not preserved; no new fit
was performed to investigate warnings. Treat biological conclusions cautiously.

## What this establishes and does not establish

E1 shows that the unchanged governed analysis components can execute validly
paired raw-count contrasts on the fixed real-data panel, and exposes substantial
withholding and missing qualification under an independent scoring rule. It
does not yet establish successful biological positive-claim preservation, exact
external donor-matched replication, reliable mechanistic/protein inference,
independent human correctness, or an unbiased genome-wide benchmark.

This attempt therefore does not presently strengthen the paper's positive-
biological-retention claim. It provides auditable counterevidence and limitations
that must be included, not tuned away. Execution is closed against reruns; E1
scientific validation remains PARTIAL. Any future remedy requires a separate
prospective version, not changes to this attempt.

Canonical evidence packets are in each `execution/<target>/` directory alongside
the exact original reply, primary results, native gates, schema and sensitivity
results. Their target-identity and separate-sensitivity context limitations must
be resolved prospectively before any future E2 comparison; E2 has not started.
Do not treat these packets as already validated for a four-arm experiment.

## Reproduction and artifacts

The frozen lock records all input/code hashes. `eval/scripts/e1/execute_e1.py`
refuses a second analysis in this attempt directory. `analyze`, `opportunities`,
and `report` were run once in that order. Read-only verification uses saved
outputs; do not rerun fit/report stages. Acquisition, source reference and
preparation scripts are under `eval/scripts/e1/`; a future run needs a new
prospective directory and authorization. Never copy the private environment
loader or credentials into artifacts. `E1_SHA256_MANIFEST.json` lists final
artifact and evaluator-source hashes; it excludes itself by construction.
"""
    (OUT/"E1_BIOLOGICAL_VALIDATION_FINAL_REPORT.md").write_text(text)
    write(OUT/"E1_FAILURE_AND_LIMITATION_TABLE.json",{"execution_failures":[],
        "scientific_validation_limits":summary["remaining_validation_limits"],
        "original_replies_and_packets_preserved_without_repair":True})
    all_files=[p for p in OUT.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    files={str(p.relative_to(ROOT)):digest(p) for p in all_files}
    files.update({str(p.relative_to(ROOT)):digest(p) for p in (ROOT/"eval/scripts/e1").glob("*.py")})
    write(OUT/"E1_SHA256_MANIFEST.json",{"status":summary["status"],"files":files})
    for p in all_files:p.chmod(0o444)
    (OUT/"E1_SHA256_MANIFEST.json").chmod(0o444)
    print(json.dumps({"status":summary["status"],"call_counts":counts,
          "manifest_sha256":digest(OUT/"E1_SHA256_MANIFEST.json"),"files":len(files)},indent=2))

if __name__=="__main__":main()
