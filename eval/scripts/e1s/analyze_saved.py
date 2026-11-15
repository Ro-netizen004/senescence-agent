"""E1-S saved-data analysis. No model generation and no statistical refitting."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import norm
from common import ROOT,E1,OUT,TARGETS,verify_lock,write
from metrics import paired_effect_status,cpm_effects,bh,median_log_ratio_factors,warning_class

def main():
    verify_lock()
    if (OUT/"SAVED_ANALYSIS_STARTED.json").exists():raise FileExistsError("Analysis already attempted")
    write(OUT/"SAVED_ANALYSIS_STARTED.json",{"new_fits":0,"new_model_replies":0,"source":"preserved E1 only"})
    eligibility=pd.read_csv(E1/"E1_TARGET_ELIGIBILITY.csv").set_index("target")
    family={r["target"]:r for r in json.loads((E1/"E1_ON_TARGET_FAMILY_A.json").read_text())}
    fit_rows=[];warning_rows=[];stability=[];long=[];gene_rows=[];numeric=[];checks=[];size_factors=[]
    for t in TARGETS:
        p=E1/"execution"/t
        full=pd.read_csv(p/"deseq2_results.csv",index_col=0)
        counts=pd.read_csv(E1/"prepared"/t/"counts.csv.gz",index_col=0)
        meta=pd.read_csv(E1/"prepared"/t/"metadata.csv",index_col=0)
        gid=eligibility.loc[t,"target_gene_id"]
        donors=int(meta.donor_id.nunique())
        design=pd.get_dummies(meta[["donor_id","perturbation"]],drop_first=True,dtype=float)
        design.insert(0,"intercept",1.)
        rank=int(np.linalg.matrix_rank(design.to_numpy()));resdf=len(meta)-rank
        original=json.loads((p/"tool_result.json").read_text())["replicate_stability"]
        significant=full.index[full.padj.fillna(1).lt(.05)]
        fitlist=[("primary",p/"deseq2_results.csv",p/"analysis.log",resdf)]
        fitlist += [(f.stem,f,f.with_suffix(".log"),2) for f in sorted((p/"paired_sensitivity").glob("*.csv"))]
        for fit_id,file,log,df_res in fitlist:
            frame=pd.read_csv(file,index_col=0)
            messages=[]
            for line_num,line in enumerate(log.read_text().splitlines(),1):
                if "Warning:" in line:
                    message=line.split("Warning:",1)[1].strip();messages.append(message)
                    warning_rows.append({"target":t,"fit":fit_id,"log_path":str(log.relative_to(ROOT)),
                        "line":line_num,"exact_warning":line,"message":message,"classification":warning_class(message),
                        "effect_on_reported_values":"UNRESOLVED; optimizer/intermediate states not saved" if "matmul" in message else "see source-specific assessment"})
            nonfinite_effect=int((~np.isfinite(frame[["log2FoldChange","lfcSE","stat"]])).any(axis=1).sum())
            fit_rows.append({"target":t,"fit":fit_id,"source":str(file.relative_to(ROOT)),"residual_df":df_res,
                "genes":len(frame),"nonfinite_effect_SE_or_stat":nonfinite_effect,
                "nonfinite_p":int((~np.isfinite(frame.pvalue)).sum()),"nonfinite_padj":int((~np.isfinite(frame.padj)).sum()),
                "mean_trend_fallback":any("Switching to a mean" in m for m in messages),
                "floating_warning_count":sum("matmul" in m for m in messages),
                "low_df_warning_count":sum("residual degrees" in m for m in messages),
                "optimizer_convergence":"NOT_RECOVERABLE_FROM_SAVED_OUTPUTS",
                "intermediate_nonfinite_propagation":"NOT_VERIFIED"})
        filt=counts.loc[:,counts.sum().ge(10)]
        sf,n_positive=median_log_ratio_factors(filt)
        base_ok=None;max_base_error=None
        if sf is not None:
            reconstructed=filt.div(sf,axis=0).mean(axis=0).reindex(full.index)
            base_ok=bool(np.allclose(reconstructed,full.baseMean,rtol=1e-7,atol=1e-12))
            max_base_error=float(np.max(np.abs(reconstructed-full.baseMean)))
            for sample in meta.index:size_factors.append({"target":t,"sample":sample,"donor":meta.loc[sample,"donor_id"],
                "group":meta.loc[sample,"perturbation"],"actual_cells":int(meta.loc[sample,"n_cells"]),
                "library_size":int(counts.loc[sample].sum()),"reconstructed_size_factor":float(sf.loc[sample]),
                "diagnostic_not_saved_optimizer_state":True})
        finite=full[["log2FoldChange","lfcSE","stat"]].notna().all(axis=1)&full.lfcSE.gt(0)
        pfinite=full.pvalue.notna()&full.stat.notna();qfinite=full.padj.notna()&full.pvalue.notna()
        check={"target":t,"sample_alignment_exact":counts.index.equals(meta.index),"raw_counts_integer_nonnegative":
            bool(np.isfinite(counts.to_numpy()).all() and counts.ge(0).all().all() and np.equal(counts,np.rint(counts)).all().all()),
            "design_rank":rank,"residual_df":resdf,"gene_filter_matches":set(filt.columns)==set(full.index),
            "wald_stat_matches":bool(np.allclose(full.loc[finite,"log2FoldChange"]/full.loc[finite,"lfcSE"],full.loc[finite,"stat"],rtol=1e-7,atol=1e-12)),
            "wald_p_matches":bool(np.allclose(2*norm.sf(full.loc[pfinite,"stat"].abs()),full.loc[pfinite,"pvalue"],rtol=1e-7,atol=1e-12)),
            "BH_matches":bool(np.allclose(bh(full.loc[qfinite,"pvalue"]),full.loc[qfinite,"padj"],rtol=1e-7,atol=1e-12)),
            "reconstructed_baseMean_matches":base_ok,"max_baseMean_absolute_difference":max_base_error,
            "median_ratio_eligible_genes":n_positive}
        checks.append(check)
        own=full.loc[gid]
        numeric.append({"target":t,"donors":donors,"samples":len(meta),"parameters":rank,"residual_df":resdf,
            "original_on_target_lfc":own.log2FoldChange,"original_on_target_SE":own.lfcSE,
            "original_on_target_raw_p":own.pvalue,"original_on_target_family_A_q":family[t]["family_a_q"],
            "original_on_target_genomewide_q":own.padj,"original_significant_genes":len(significant),
            "original_downstream_significant_excluding_target":int(full.drop(index=gid).padj.lt(.05).sum()),
            "on_target_95CI_lower":own.log2FoldChange-1.959963984540054*own.lfcSE,
            "on_target_95CI_upper":own.log2FoldChange+1.959963984540054*own.lfcSE,
            "independent_R_status":"UNAVAILABLE_NO_R_RUNTIME_OR_RUNNING_DOCKER",
            "independent_R_lfc":None,"independent_R_SE":None,"independent_R_p":None,"independent_R_q":None,
            "independent_R_DEG_count":None,"independent_R_shared_gene_count":None,"independent_R_Jaccard":None,
            "independent_R_significance_disagreement":None,"numerical_reliability":"UNRESOLVED"})
        if donors!=4:
            stability.append({"target":t,"original_significant_genes":len(significant),"native_verdict":original["verdict"],
                              "paired_fit_status":"NOT_AVAILABLE_THREE_DONORS","paired_refit_stable_fraction":None})
            continue
        lfc=[];se=[];q=[];raw=[]
        for donor,file,_,_ in fitlist[1:]:
            omitted=pd.read_csv(file,index_col=0).reindex(significant)
            lfc.append(omitted.log2FoldChange.rename(donor));se.append(omitted.lfcSE.rename(donor))
            q.append(omitted.padj.rename(donor));raw.append(omitted.pvalue.rename(donor))
            for gene,r in omitted.iterrows():
                long.append({"target":t,"gene":gene,"omitted_donor":donor,"full_lfc":full.loc[gene,"log2FoldChange"],
                    "full_SE":full.loc[gene,"lfcSE"],"omitted_lfc":r.log2FoldChange,"omitted_SE":r.lfcSE,
                    "omitted_raw_p":r.pvalue,"omitted_padj":r.padj,
                    "omitted_95CI_lower":r.log2FoldChange-1.959963984540054*r.lfcSE,
                    "omitted_95CI_upper":r.log2FoldChange+1.959963984540054*r.lfcSE,
                    "source_file":str(file.relative_to(ROOT))})
        lfc=pd.DataFrame(lfc);se=pd.DataFrame(se);q=pd.DataFrame(q)
        paired=paired_effect_status(full.loc[significant,"log2FoldChange"],lfc)
        nfull,nsingle=cpm_effects(counts,meta,significant,False)
        _,npaired=cpm_effects(counts,meta,significant,True)
        native=paired_effect_status(nfull,nsingle)
        cpm_paired=paired_effect_status(nfull,npaired)
        original_native=pd.DataFrame(original["genes"]).set_index("gene").reindex(significant)
        exact=bool(native.paired_stable.eq(original_native.stable).all())
        a=native.paired_stable;b=paired.paired_stable;both=a&b;union=a|b
        sig_all=q.lt(.05).all(axis=0)&q.notna().all(axis=0)
        magnitude_sd=lfc.std(axis=0)
        for gene in significant:
            gene_rows.append({"target":t,"gene":gene,"on_target":gene==gid,
                "full_deseq2_lfc":full.loc[gene,"log2FoldChange"],"full_logCPM_effect":nfull.loc[gene],
                "full_baseline_sign_agrees":bool(np.sign(full.loc[gene,"log2FoldChange"])==np.sign(nfull.loc[gene])),
                "native_single_CPM_stable":bool(a.loc[gene]),"paired_CPM_stable":bool(cpm_paired.loc[gene,"paired_stable"]),
                "paired_DE_direction_stable":bool(paired.loc[gene,"direction_stable"]),
                "paired_DE_minimum_effect_retention":paired.loc[gene,"minimum_effect_retention"],
                "paired_DE_stable":bool(b.loc[gene]),"all_four_omissions_significant":bool(sig_all.loc[gene]),
                "omission_lfc_SD":magnitude_sd.loc[gene],"maximum_omission_SE":se[gene].max(),
                "all_omissions_finite":bool(paired.loc[gene,"all_omissions_finite"])})
        stability.append({"target":t,"original_significant_genes":len(significant),"native_verdict":original["verdict"],
            "paired_fit_status":"FOUR_PRESERVED_FITS","native_reconstructed_exact":exact,
            "native_stable_fraction":float(a.mean()),"paired_CPM_stable_fraction":float(cpm_paired.paired_stable.mean()),
            "paired_refit_direction_fraction":float(paired.direction_stable.mean()),"paired_refit_stable_fraction":float(b.mean()),
            "paired_refit_analogue_verdict":"stable" if b.mean()>=.8 else "unstable",
            "significant_in_all_four_fraction":float(sig_all.mean()),"both_stable":int(both.sum()),
            "native_only":int((a&~b).sum()),"paired_only":int((~a&b).sum()),"neither":int((~a&~b).sum()),
            "classification_agreement":float(a.eq(b).mean()),"stable_set_Jaccard":float(both.sum()/union.sum()) if union.sum() else None,
            "full_CPM_vs_DE_sign_disagreements":int(np.sign(nfull).ne(np.sign(full.loc[significant,"log2FoldChange"])).sum()),
            "not_an_original_gate_reclassification":True})
    for name,rows in [("E1S_NUMERICAL_WARNINGS_AUDIT.csv",warning_rows),("E1S_FIT_DIAGNOSTICS.csv",fit_rows),
        ("E1S_NUMERICAL_ROBUSTNESS.csv",numeric),("E1S_NATIVE_VS_PAIRED_STABILITY.csv",stability),
        ("E1S_DONOR_SENSITIVITY_SUMMARY.csv",gene_rows),("E1S_DONOR_SENSITIVITY_LONG.csv",long),
        ("E1S_NORMALIZATION_DIAGNOSTICS.csv",size_factors)]:pd.DataFrame(rows).to_csv(OUT/name,index=False)
    original_warnings=pd.read_csv(E1/"E1_NUMERICAL_WARNINGS.csv")
    warn_match=len(original_warnings)==len(warning_rows) and sorted(original_warnings.exact_warning)==sorted(r["exact_warning"] for r in warning_rows)
    concordance=pd.read_csv(E1/"E1_BIOLOGICAL_CONCORDANCE.csv")
    reference_checks={}
    for assay,group in concordance.groupby("assay"):
        recomputed=np.sign(group.e1_log2FC).eq(np.sign(group.log2_effect))
        reference_checks[assay]={"agree":int(recomputed.sum()),"denominator":len(group),"original_matches":bool(recomputed.eq(group.direction_agreement).all())}
    verification={"new_fits":0,"new_model_replies":0,"fit_count":len(fit_rows),"warning_count":len(warning_rows),
        "warnings_match_original_inventory":warn_match,"target_checks":checks,"reference_checks":reference_checks,
        "native_checks":[{"target":r["target"],"matches":r["native_reconstructed_exact"]} for r in stability if "native_reconstructed_exact" in r]}
    write(OUT/"E1S_INDEPENDENT_VERIFICATION.json",verification)
    print(json.dumps({"fits_audited":len(fit_rows),"warnings":len(warning_rows),"warning_inventory_matches":warn_match,
          "reference_checks":reference_checks,"new_fits":0},indent=2))

if __name__=="__main__":main()
