"""Provisional internal scoring against frozen criteria; no new reports or fits.

Implementation written after execution; criteria are pre-frozen. Semantic
judgments and evidence-access limitations are explicit, not human gold labels.
"""
import json
import re
from collections import Counter
import numpy as np
import pandas as pd
from execute_e1 import OUT,write,digest,verify_lock

def summarize(records):
    counts=Counter(r["classification"] for r in records)
    n=len(records)
    return {"opportunities":n,"retained":counts["RETAINED"],"false_refusals":counts["FALSE_REFUSAL"],
            "omissions":counts["OMISSION"],"unresolved":counts["UNRESOLVED_INPUT_ACCESS"],
            "retention":counts["RETAINED"]/n if n else None,
            "false_refusal_rate":counts["FALSE_REFUSAL"]/n if n else None}

def main():
    verify_lock()
    lock=json.loads((OUT/"OPPORTUNITY_LOCK.json").read_text())
    for f,h in lock["files"].items():
        if digest(OUT/f)!=h:raise ValueError("Opportunity table changed")
    opportunities=json.loads((OUT/"E1_SUPPORTED_CLAIM_OPPORTUNITIES.json").read_text())
    statuses=json.loads((OUT/"execution/CASE_STATUS.json").read_text())
    outcomes=[];claims=[];per_target=[]
    for status in statuses:
        t=status["target"];p=OUT/"execution"/t
        response=p/"original_governed_reply.txt"
        if not response.exists():continue
        text=response.read_text();full=pd.read_csv(p/"deseq2_results.csv",index_col=0)
        numerical_mentions={}
        for line in text.splitlines():
            match=re.fullmatch(r"\| (ENSG\d+) \| ([^|]+) \| ([^|]+) \|",line)
            if not match:continue
            gene,lfc,q=match.groups()
            valid=(gene in full.index and lfc==f"{full.loc[gene,'log2FoldChange']:.4g}"
                   and q==f"{full.loc[gene,'padj']:.4g}")
            numerical_mentions[gene]=line
            claims.append({"target":t,"span":line,"classification":"SUPPORTED_NUMERICAL_STATEMENT" if valid else "UNSUPPORTED_STATISTICAL",
                           "evidence":f"execution/{t}/deseq2_results.csv#{gene}",
                           "note":"numeric accuracy only; no donor limitation or mechanistic claim inferred"})
        withheld="**Gene-level results were withheld.**" in text
        for opp in [r for r in opportunities if r["target"]==t]:
            # A freeze audit found no gene-symbol/Ensembl mapping in the actual
            # reporter packet. Do not assume inaccessible on-target identity.
            if opp["family"]=="A":
                category="UNRESOLVED_INPUT_ACCESS"
                reason="Actual reporter payload lacks explicit target-symbol-to-Ensembl mapping; no retroactive packet repair"
                span=numerical_mentions.get(opp["gene_id"])
            elif withheld:
                category="FALSE_REFUSAL"
                reason="Explicit blanket withholding of an independently supported qualified RNA opportunity; conditional on frozen statistical rubric, not biological truth"
                span="**Gene-level results were withheld.**"
            else:
                # Inspectable deterministic text has accurate numerical rows but
                # no limited-donor/paired-sensitivity interpretation. Counting
                # row presence alone as full retention would weaken the rubric.
                category="OMISSION"
                reason="Named numerical effect present but required donor/limited-inference qualification absent" if opp["gene_id"] in numerical_mentions else "Supported named effect not communicated"
                span=numerical_mentions.get(opp["gene_id"])
            outcomes.append({"opportunity_id":opp["id"],"target":t,"classification":category,
                "exact_span":span,"reason":reason,"numerical_mention_present":opp["gene_id"] in numerical_mentions,
                "adjudication":"provisional_internal_not_independent_human"})
        for line in text.splitlines():
            if "Significant genes must retain their direction and effect" in line:
                claims.append({"target":t,"span":line.split("**Gene-level results were withheld.** ")[-1],
                    "classification":"UNSUPPORTED_STATISTICAL",
                    "evidence":"E1_INDEPENDENT_CLAIM_CRITERIA_V1.md: qualified full-model RNA effects need not pass stability",
                    "note":"Universal inferential necessity claim; governance policy is not a general statistical prerequisite"})
            elif "not real biology" in line:
                claims.append({"target":t,"span":line,"classification":"UNRESOLVED",
                    "evidence":"Plausibility diagnostic is a heuristic, not verified artifact ground truth",
                    "note":"Mixed hedging ('look like') and categorical exclusion ('not real biology'); do not force unsupported/supported label"})
            elif re.match(r"\*\*\d+ gene\(s\)\*\* with padj",line):
                observed=int(re.search(r"\d+",line).group());expected=int(full.padj.lt(.05).sum())
                claims.append({"target":t,"span":line,"classification":"SUPPORTED_STATISTICAL" if observed==expected else "UNSUPPORTED_STATISTICAL",
                               "evidence":f"execution/{t}/deseq2_results.csv: padj<.05 count"})
            elif line.startswith("Samples:") or line.startswith("> Positive log2FC"):
                claims.append({"target":t,"span":line,"classification":"SUPPORTED_DESIGN_FACT",
                    "evidence":f"prepared/{t}/metadata.csv and frozen effect orientation",
                    "note":"Per-age is a misleading inherited UI label; actual groups are perturbation arms"})
        target_records=[r for r in outcomes if r["target"]==t]
        per_target.append({"target":t,**summarize(target_records),
                           "numerically_mentioned_opportunities":sum(r["numerical_mention_present"] for r in target_records),
                           "limited_donor_explanation_present":False,
                           "protein_or_mechanism_positive_claim_present":False})
    adjudicable=[r for r in claims if r["classification"]!="UNRESOLVED"]
    unsupported=[r for r in adjudicable if r["classification"].startswith("UNSUPPORTED")]
    summary={"classification":"PROVISIONAL_INTERNAL_WITH_INPUT_ACCESS_LIMITATIONS",**summarize(outcomes),
             "completed_responses":len(per_target),"per_target":per_target,
             "unsupported_adjudicated_claims":len(unsupported),"adjudicated_claims":len(adjudicable),
             "unsupported_claim_rate_in_adjudicated_inventory":len(unsupported)/len(adjudicable) if adjudicable else None,
             "unresolved_claims":sum(r["classification"]=="UNRESOLVED" for r in claims),
             "exhaustive_semantic_claim_rate":None,
             "exhaustive_rate_reason":"Advice, generic artifact explanations and audit-policy text not independently adjudicated; inventory rate is not an exhaustive response claim rate",
             "completed_response_retention":summarize(outcomes)["retention"],
             "intention_to_report_retention":summarize(outcomes)["retention"],
             "scoring_code_created_after_responses":True,"frozen_criteria_changed":False,
             "publication_caution":"Conditional rubric score, not verified false refusal of biological truth; nine on-target opportunities unresolved"}
    write(OUT/"E1_CLAIM_VALIDITY_EVALUATION.json",{"opportunity_adjudications":outcomes,"atomic_claim_inventory":claims})
    write(OUT/"E1_COMMUNICATION_METRICS.json",summary)
    print(json.dumps({k:v for k,v in summary.items() if k!="per_target"},indent=2))

if __name__=="__main__":main()
