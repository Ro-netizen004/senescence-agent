"""Prospectively specified E1-S diagnostics; no production governance imports."""
import numpy as np
import pandas as pd

def paired_effect_status(full,omissions):
    """Rows are omitted donors; columns fixed original primary-significant genes."""
    finite=np.isfinite(omissions).all(axis=0)&np.isfinite(full)&full.ne(0)
    direction=(np.sign(omissions)==np.sign(full)).all(axis=0)&finite
    ratio=omissions.abs().min(axis=0).div(full.abs().replace(0,np.nan))
    stable=direction&ratio.ge(.5)&finite
    return pd.DataFrame({"direction_stable":direction,"minimum_effect_retention":ratio,
                         "all_omissions_finite":finite,"paired_stable":stable})

def cpm_effects(counts,meta,genes,paired):
    frame=np.log2(counts.loc[:,genes].div(counts.sum(axis=1),axis=0)*1e6+1)
    def effect(x,m):return x[m.perturbation.eq("targeting")].mean()-x[m.perturbation.eq("NTC")].mean()
    full=effect(frame,meta)
    omissions={}
    units=sorted(meta.donor_id.unique()) if paired else list(meta.index)
    for unit in units:
        keep=~meta.donor_id.eq(unit) if paired else meta.index!=unit
        omissions[str(unit)]=effect(frame.loc[keep],meta.loc[keep])
    return full,pd.DataFrame(omissions).T

def bh(p):
    p=np.asarray(p,dtype=float);order=np.argsort(p)
    out=np.empty(len(p))
    out[order]=np.minimum.accumulate((p[order]*len(p)/np.arange(1,len(p)+1))[::-1])[::-1].clip(0,1)
    return out

def median_log_ratio_factors(counts):
    positive=counts.gt(0).all(axis=0)
    if not positive.any():return None,0
    log=np.log(counts.loc[:,positive])
    return np.exp(log.sub(log.mean(axis=0),axis=1).median(axis=1)),int(positive.sum())

def warning_class(message):
    if "residual degrees of freedom" in message:return "EXPECTED_BUT_IMPORTANT_STATISTICAL_LIMITATION"
    if "dispersion trend" in message:return "POTENTIAL_NUMERICAL_RELIABILITY_CONCERN"
    if "matmul" in message:return "UNRESOLVED_WITHOUT_ADDITIONAL_NUMERICAL_EVIDENCE"
    return "UNRESOLVED_WITHOUT_ADDITIONAL_NUMERICAL_EVIDENCE"
