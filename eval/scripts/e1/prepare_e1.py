"""Outcome-blind E1 feasibility and exact donor aggregation."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from scipy import sparse
from extract_panel import TARGETS, validate_counts
from remote_feasibility import ROOT, OUT

sys.path.insert(0,str(ROOT/"backend"))
from agent.design_validation import validate_factor_design

def mapping_matches(row, source):
    """Official NTC records have a blank gene ID, encoded as NTC in HDF5."""
    if str(source.perturbed_gene_name) != str(row.perturbed_gene_name):
        return False
    if row.guide_type == "non-targeting":
        return (row.perturbed_gene_name == "NTC" and row.perturbed_gene_id == "NTC"
                and pd.isna(source.perturbed_gene_id))
    return (row.guide_type == "targeting" and pd.notna(source.perturbed_gene_id)
            and str(source.perturbed_gene_id) == str(row.perturbed_gene_id))

def technical_mask(obs, threshold):
    return (obs.n_cells.ge(5) & obs.total_counts.ge(threshold) & obs.total_counts.gt(0)
            & ~obs.guide_id.astype(str).str.contains("multi-guide",case=False))

def aggregate(counts, obs, target, threshold):
    """Sum guides into paired donor samples; do not use efficacy/DE flags."""
    validate_counts(counts)
    keep = technical_mask(obs,threshold)
    ntc = obs.guide_type.eq("non-targeting") & obs.perturbed_gene_name.eq("NTC")
    treatment = obs.guide_type.eq("targeting") & obs.perturbed_gene_name.eq(target)
    donor_rows=[]
    vectors=[]
    metadata=[]
    for donor in sorted(obs.donor_id.unique()):
        masks={"NTC": keep & ntc & obs.donor_id.eq(donor), "targeting": keep & treatment & obs.donor_id.eq(donor)}
        cells={arm:int(obs.loc[m,"n_cells"].sum()) for arm,m in masks.items()}
        complete=min(cells.values())>=20
        batches={arm:sorted(obs.loc[m,"10xrun_id"].unique().tolist()) for arm,m in masks.items()}
        if complete and batches["NTC"] != batches["targeting"]:
            complete=False
        donor_rows.append({"target":target,"donor_id":donor,"condition":"Stim8hr",
                           "targeting_cells":cells["targeting"],"ntc_cells":cells["NTC"],
                           "targeting_guides":";".join(obs.loc[masks["targeting"],"guide_id"]),
                           "ntc_guides":";".join(obs.loc[masks["NTC"],"guide_id"]),
                           "targeting_n_guides":int(masks["targeting"].sum()),
                           "ntc_n_guides":int(masks["NTC"].sum()),
                           "targeting_batch":";".join(batches["targeting"]),"ntc_batch":";".join(batches["NTC"]),
                           "targeting_library_size":int(counts[masks["targeting"].to_numpy()].sum()),
                           "ntc_library_size":int(counts[masks["NTC"].to_numpy()].sum()),
                           "complete_pair":complete,
                           "reason":"eligible" if complete else "fewer_than_20_cells_in_either_arm_or_batch_mismatch"})
        if complete:
            for arm in ("NTC","targeting"):
                mask=masks[arm]
                vectors.append(np.asarray(counts[mask.to_numpy()].sum(axis=0)).ravel())
                metadata.append({"sample_id":f"{donor}__{arm}","donor_id":donor,
                                 "perturbation":arm,"n_cells":cells[arm],"batch":";".join(batches[arm]),
                                 "source_rows":";".join(obs.index[mask].astype(str)),
                                 "source_guides":";".join(obs.loc[mask,"guide_id"])})
    columns=["sample_id","donor_id","perturbation","n_cells","batch","source_rows","source_guides"]
    return (np.asarray(vectors,dtype=np.int64).reshape((-1,counts.shape[1])),
            pd.DataFrame(metadata,columns=columns).set_index("sample_id"),donor_rows)

def main():
    data=OUT/"data"
    obs=pd.read_csv(data/"Stim8hr_panel_and_all_NTC_obs.csv",index_col=0)
    var=pd.read_csv(data/"expression_genes.csv",index_col=0)
    counts=sparse.load_npz(data/"Stim8hr_panel_and_all_NTC_counts.npz")
    validate_counts(counts)
    if counts.shape != (len(obs),len(var)) or not obs.index.is_unique or not var.index.is_unique:
        raise ValueError("nonunique identifiers or shape mismatch")
    if not obs.culture_condition.eq("Stim8hr").all():
        raise ValueError("unexpected condition")
    all_obs=pd.read_csv(OUT/"sources/pseudobulk_obs.csv",index_col=0)
    threshold=float(all_obs.loc[all_obs.culture_condition.eq("Stim8hr"),"total_counts"].quantile(0.005))
    curated=pd.read_csv(OUT/"sources/metadata/sgRNA_library_curated.csv").set_index("sgrna_id")
    if not curated.index.is_unique:
        raise ValueError("nonunique curated guide mapping")
    for row in obs.itertuples():
        if row.guide_id not in curated.index:
            raise ValueError("guide missing curated identity: "+row.guide_id)
        source=curated.loc[row.guide_id]
        if not mapping_matches(row,source):
            raise ValueError("curated mapping mismatch: "+row.guide_id)
    coverage=[]
    targets=[]
    output=OUT/"prepared"
    output.mkdir(exist_ok=True)
    for target in TARGETS:
        values,meta,rows=aggregate(counts,obs,target,threshold)
        genes=var.index.astype(str)
        frame=pd.DataFrame(values,index=meta.index,columns=genes)
        validation=(validate_factor_design(meta,"perturbation",["donor_id"]) if len(meta)
                    else {"full_rank":False,"rank":0,"reason":"no complete donor pairs"})
        target_ids=sorted(obs.loc[obs.perturbed_gene_name.eq(target),"perturbed_gene_id"].unique().tolist())
        n_pairs=len(meta)//2
        eligible=n_pairs>=3 and validation["full_rank"] and len(target_ids)==1
        for row in rows:
            row.update(target_gene_id=";".join(target_ids),target_gene_present=all(g in genes for g in target_ids),
                       design_rank=validation["rank"],n_complete_pairs=n_pairs)
        coverage.extend(rows)
        dest=output/target
        dest.mkdir(exist_ok=True)
        frame.to_csv(dest/"counts.csv.gz",compression={"method":"gzip","mtime":0})
        meta.to_csv(dest/"metadata.csv")
        (dest/"design.json").write_text(json.dumps(validation,indent=2)+"\n")
        targets.append({"target":target,"target_gene_id":";".join(target_ids),"status":"ELIGIBLE" if eligible else "INELIGIBLE",
                        "complete_donor_pairs":n_pairs,"n_samples":len(meta),"four_donor_sensitivity_eligible":n_pairs==4,
                        "target_gene_present":all(g in genes for g in target_ids),"design_rank":validation["rank"],
                        "reason":"count, mapping, pairing and rank checks passed" if eligible else "fewer than 3 pairs or invalid mapping/design"})
    pd.DataFrame(coverage).to_csv(OUT/"E1_TARGET_DONOR_COVERAGE.csv",index=False)
    pd.DataFrame(targets).to_csv(OUT/"E1_TARGET_ELIGIBILITY.csv",index=False)
    summary={"targets":targets,"selected_count_shape":list(counts.shape),"guide_min_cells":5,"donor_arm_min_cells":20,
             "minimum_pairs":3,"condition_count_quantile":0.005,"condition_count_threshold":threshold,
             "efficacy_filter_used":False,"keep_for_DE_used":False,"keep_test_genes_used":False,
             "integer_counts_verified":True,"guide_mapping_verified":True,"new_de_fits":0,"generated_responses":0}
    (OUT/"FEASIBILITY_METRICS.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))

if __name__ == "__main__":
    main()
