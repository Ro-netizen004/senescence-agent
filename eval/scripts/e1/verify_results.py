"""Independent arithmetic/provenance checks on saved E1 outputs; no fits/APIs."""
import json
import numpy as np
import pandas as pd
from scipy.stats import norm
from execute_e1 import OUT,ROOT,digest,write,verify_lock

def bh(values):
    values=np.asarray(values,dtype=float);order=np.argsort(values)
    ranked=values[order]*len(values)/np.arange(1,len(values)+1)
    adjusted=np.minimum.accumulate(ranked[::-1])[::-1].clip(0,1)
    result=np.empty(len(values));result[order]=adjusted
    return result

def main():
    verify_lock()
    statuses=json.loads((OUT/"execution/CASE_STATUS.json").read_text())
    checks=[];rows=[];references=pd.read_csv(OUT/"E1_BIOLOGICAL_REFERENCE.csv")
    eligibility=pd.read_csv(OUT/"E1_TARGET_ELIGIBILITY.csv").set_index("target")
    pvalues=[]
    for s in statuses:
        t=s["target"];p=OUT/"execution"/t/"deseq2_results.csv"
        if not p.exists():
            pvalues.append(1.);checks.append({"target":t,"status":"NO_RESULT"});continue
        df=pd.read_csv(p,index_col=0)
        target_id=eligibility.loc[t,"target_gene_id"]
        rawp=df.loc[target_id,"pvalue"] if target_id in df.index else np.nan
        pvalues.append(float(rawp) if np.isfinite(rawp) else 1.)
        finite=df[["log2FoldChange","lfcSE","stat"]].notna().all(axis=1)&df.lfcSE.gt(0)
        wald=np.allclose(df.loc[finite,"log2FoldChange"]/df.loc[finite,"lfcSE"],df.loc[finite,"stat"],rtol=1e-8,atol=1e-8)
        pp=df.pvalue.notna()&df.stat.notna()
        pcheck=np.allclose(2*norm.sf(np.abs(df.loc[pp,"stat"])),df.loc[pp,"pvalue"],rtol=1e-7,atol=1e-14)
        adjusted=df.padj.notna()&df.pvalue.notna()
        qcheck=np.allclose(bh(df.loc[adjusted,"pvalue"]),df.loc[adjusted,"padj"],rtol=1e-7,atol=1e-14)
        checks.append({"target":t,"wald_statistic_matches_lfc_over_se":bool(wald),
                       "two_sided_wald_p_matches":bool(pcheck),"BH_matches_finite_adjusted_family":bool(qcheck),
                       "genes":len(df),"finite_adjusted_genes":int(adjusted.sum()),
                       "interpretation":"independent filtering/Cooks exclusions retained; no refit"})
        for _,r in references[references.target.eq(t)].iterrows():
            actual=df.loc[r.gene_id] if r.gene_id in df.index else None
            valid=actual is not None and np.isfinite(actual.log2FoldChange)
            rows.append({**r.to_dict(),"e1_log2FC":float(actual.log2FoldChange) if valid else None,
                         "e1_padj":float(actual.padj) if valid else None,
                         "direction_agreement":bool(np.sign(actual.log2FoldChange)==np.sign(r.log2_effect)) if valid else None,
                         "both_significant_at_respective_registered_thresholds":bool(actual.padj<.05 and r.adjusted_p<.1) if valid else False,
                         "matched_e1_result":valid})
    family=json.loads((OUT/"E1_ON_TARGET_FAMILY_A.json").read_text())
    family_ok=np.allclose(bh(pvalues),[r["family_a_q"] for r in family])
    record={"no_new_fits":True,"no_api_calls":True,"target_checks":checks,
            "family_a_nine_test_BH_matches":bool(family_ok),"frozen_inputs_match":True}
    write(OUT/"E1_INDEPENDENT_NUMERICAL_VERIFICATION.json",record)
    pd.DataFrame(rows).to_csv(OUT/"E1_BIOLOGICAL_CONCORDANCE.csv",index=False)
    print(json.dumps(record,indent=2))

if __name__=="__main__":main()
