"""Outcome-free packet and frozen-policy checks. Does not render real cases."""
from collections import Counter
import json
import pandas as pd
from common import *

FORBIDDEN={'verdict','gold','reply','claim_violations','false_discovery','inference_state','admissible','licensed_claim'}
def keys(x):
    if isinstance(x,dict):
        for k,v in x.items():yield k;yield from keys(v)
    elif isinstance(x,list):
        for v in x:yield from keys(v)

def historical(m):
    source=read(ROOT/m['source_path'])
    if m['family']=='F1':
        i=int(m['source_selector'].split('[')[1].split(']')[0]);r=source['permutations'][i]
        return r['inference_state'],r['reply'],r.get('result_withheld')
    if m['family'] in ['F2','F3']:
        r=source['score'];state=r['inference_state']
        t=r['tool_call']['result'];withheld=t['result_plausibility'].get('verdict')=='suspect' or t['replicate_stability'].get('verdict') in ['unstable','insufficient_evidence','assessment_failed']
        return state,r['reply'],withheld
    p=E1/'execution'/m['case_id'][3:]
    schema=read(p/'output_schema.json')[0]
    return schema['inference_state'],(p/'original_governed_reply.txt').read_text(),schema['result_withheld']

def validate():
    from agent.inference_state import apply_inference_state
    from agent.output_schema import build_output_schema
    manifest=[json.loads(s) for s in (OUT/'E2_CASE_MANIFEST.jsonl').read_text().splitlines()]
    assert Counter(m['family'] for m in manifest)=={'F1':78,'F2':10,'F3':5,'F4':9}
    rows=[]
    for m in manifest:
        p=read(ROOT/m['packet_path']);d=read(OUT/f'arm_d_inputs/{m["case_id"]}.json')
        assert sha(ROOT/m['packet_path'])==m['packet_sha256']
        assert not (FORBIDDEN & set(keys(p))),m['case_id']
        assert d['tool']['results']==p['statistics']['rows']
        assert p['numerical_warnings'],m['case_id']
        state=apply_inference_state('run_deseq2',d['tool'],d['args'])
        schema=build_output_schema('run_deseq2',state,d['args'])
        old,reply,withheld=historical(m)
        assert schema['inference_state']==old,(m['case_id'],schema['inference_state'],old)
        assert schema.get('result_withheld',False)==bool(withheld),m['case_id']
        # Historical text is only hashed and labeled; never copied to new arm outputs.
        rows.append({'case_id':m['case_id'],'family':m['family'],'context_match':'same source allocation/target',
            'historical_state':old,'current_frozen_policy_state':schema['inference_state'],
            'historical_withheld':withheld,'historical_reply_sha256':hashlib.sha256(reply.encode()).hexdigest(),
            'historical_source':m['source_path'],'same_information_interface':False,
            'scope':'SECONDARY_HISTORICAL_DIAGNOSTIC_NOT_NEW_E2_OBSERVATION'})
    return rows

if __name__=='__main__':
    rows=validate()
    write(OUT/'E2_INTERFACE_VALIDATION.json',{'time':now(),'cases':len(rows),'policy_mismatches':0,
        'leakage_failures':0,'canonical_equivalence_before_licenses':True,'new_scored_responses':0})
    pd.DataFrame(rows).to_csv(OUT/'E2_HISTORICAL_INTERFACE_DIAGNOSTIC.csv',index=False)
    print(encode({'cases':len(rows),'policy_mismatches':0,'status':'PASS'}))
