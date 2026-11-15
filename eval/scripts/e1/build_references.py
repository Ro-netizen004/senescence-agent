"""Freeze external evidence inputs before new E1 analyses; not agent gold labels."""
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import ttest_1samp
from statsmodels.stats.multitest import multipletests
from remote_feasibility import OUT
from extract_panel import TARGETS

INTERACTIONS={"IL10":["MED24","KDM1A","NFKB2","GATA3","SGF29","ELOB","MEN1"],
              "IL21":["CYB5R4","MED24","KDM1A","NFKB2","ATP2A2"]}

def main():
    dest=OUT/"E1_BIOLOGICAL_REFERENCE.csv"
    if dest.exists():
        raise FileExistsError(dest)
    source=OUT/"sources/metadata/suppl_tables"
    var=pd.read_csv(OUT/"data/expression_genes.csv",index_col=0)
    symbols=var.gene_name.to_dict()
    ids={v:k for k,v in symbols.items()}
    bulk=pd.read_csv(source/"IL10IL21bulkRNAseq_DESeq2_results_bygene.csv")
    rows=[]
    for target in TARGETS:
        for outcome in [target,"IL10","IL21"]:
            hit=bulk[(bulk.contrast==target)&(bulk.variable==ids[outcome])]
            if len(hit)!=1:
                raise ValueError(f"Nonunique/missing external RNA row: {target}/{outcome}")
            i=hit.index[0]; r=hit.iloc[0]
            rows.append(dict(target=target,outcome=outcome,gene_id=ids[outcome],assay="arrayed_bulk_RNA",
                condition="day10; 8h CD3/CD28/CD2 ImmunoCult restimulation",
                donor_set="NOT VERIFIED from aggregate DE table",contrast="targeting / non-targeting",
                log2_effect=r.log_fc,p_value=r.p_value,adjusted_p=r.adj_p_value,
                reference_significance_threshold=0.1,significant=bool(r.adj_p_value<0.1),
                source_file=str((source/"IL10IL21bulkRNAseq_DESeq2_results_bygene.csv").relative_to(OUT)),
                source_rows=str(i+2),separate_material=True,
                estimand_match="RNA/time/stimulation matched; guide-aware donor+PC1 model differs; exact donor membership unverified",
                comparison_class="qualified_direction_comparison_not_exact_replication"))
    flow=pd.read_csv(source/"IL10_IL21_arrayed_validation_combined.csv")
    flow["source_row"]=np.arange(len(flow))+2
    ntc=flow[flow.Perturbation.str.contains("NTC")].groupby(["Donor","Batch"])[["IL10_perc","IL21_perc"]].mean()
    flow=flow.join(ntc,on=["Donor","Batch"],rsuffix="_ntc")
    for cytokine,targets in INTERACTIONS.items():
        pending=[]
        for target in targets:
            selected=flow[flow.Perturbation.str.match(rf"^{target}-\d+$")]
            effect=np.log2(selected[f"{cytokine}_perc"]/selected[f"{cytokine}_perc_ntc"])
            if not np.isfinite(effect).all() or len(effect)<2:
                raise ValueError("Missing/invalid published flow ratios")
            pending.append(dict(target=target,outcome=cytokine,gene_id=ids[cytokine],assay="intracellular_flow",
                condition="day10; 6h Activation Cocktail plus Brefeldin A",donor_set=";".join(sorted(selected.Donor.unique())),
                contrast="percent-positive targeting / donor-batch mean NTC",
                log2_effect=float(effect.mean()),p_value=float(ttest_1samp(effect,0).pvalue),
                reference_significance_threshold=0.1,
                source_file=str((source/"IL10_IL21_arrayed_validation_combined.csv").relative_to(OUT)),
                source_rows=";".join(selected.source_row.astype(str)),separate_material=True,
                estimand_match="Different assay and stimulation duration/reagent; not a direct RNA counterpart",
                comparison_class="contextual_only; author notebook summary reproduced; guide/donor observations not independent"))
        adjusted=multipletests([r["p_value"] for r in pending],method="fdr_bh")[1]
        for r,q in zip(pending,adjusted):
            r.update(adjusted_p=float(q),significant=bool(q<.1))
        rows.extend(pending)
    pd.DataFrame(rows).to_csv(dest,index=False)
    guides=pd.read_csv(OUT/"data/Stim8hr_panel_and_all_NTC_obs.csv",index_col=0)
    selected=set(guides.loc[guides.perturbed_gene_name.isin(TARGETS),"guide_id"])
    warnings=pd.read_csv(source/"sgrna_library_metadata.suppl_table.csv")
    warnings=warnings[warnings.sgRNA.isin(selected)].copy()
    if len(warnings)!=len(selected) or set(warnings.sgRNA)!=selected:
        raise ValueError("Incomplete guide-design audit")
    warnings.to_csv(OUT/"E1_GUIDE_DESIGN_WARNINGS.csv",index=False)
    files=[dest,OUT/"E1_GUIDE_DESIGN_WARNINGS.csv"]
    record={"new_e1_de_fits":0,"new_agent_responses":0,"reference_rows":len(rows),
            "guide_warning_rows":len(warnings),"files":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            "bulk_donor_membership":"NOT VERIFIED; must not claim exact donor-matched independent validation",
            "flow_statistics":"Reconstruction of published notebook cells 23,25,27 before E1 outcomes; not E1 DE analysis"}
    with (OUT/"REFERENCE_BUILD_RECORD.json").open("x") as h:
        json.dump(record,h,indent=2);h.write("\n")
    print(json.dumps(record,indent=2))

if __name__=="__main__":
    main()
