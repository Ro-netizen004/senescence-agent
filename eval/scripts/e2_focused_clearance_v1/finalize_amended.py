"""Path/schema adapter for frozen E2 scoring/aggregation. Never generates reports.

Imports the frozen scoring and independent aggregation implementations unchanged.
Output is a new sibling analysis directory; sealed execution is never edited.
"""
import json
import sys
from collections import defaultdict, Counter
from pathlib import Path
from common import ROOT, OUT, read, write, textfile, sha, encode, now
from integration import DEST as AMENDMENT
from privacy_export import DEST as EXPORT
from scoring import score
from finalize import aggregate, verify_aggregation_independently
from orchestrator import verify_amendment, verify_manifest, seal


def paired(scores, manifest):
    by={(s['case_id'],s['arm']):s for s in scores}; pairs=[]
    for family in ['F1','F2','F3','F4']:
        cases=[m['case_id'] for m in manifest if m['family']==family]
        for baseline in ['B','C']:
            complete=[c for c in cases if by[c,'D']['status']==by[c,baseline]['status']=='SUCCESS']
            d_only=sum(by[c,'D']['unsupported_screen_event'] and not by[c,baseline]['unsupported_screen_event'] for c in complete)
            b_only=sum(by[c,baseline]['unsupported_screen_event'] and not by[c,'D']['unsupported_screen_event'] for c in complete)
            eligible=[c for c in cases if by[c,'D']['opportunities']]
            diffs=[(by[c,'D']['retained']-by[c,baseline]['retained'])/by[c,'D']['opportunities'] for c in eligible]
            complete_diffs=[(by[c,'D']['retained']-by[c,baseline]['retained'])/by[c,'D']['opportunities'] for c in eligible if c in complete]
            pairs.append({'family':family,'comparison':'D-'+baseline,'planned_pairs':len(cases),'completed_pairs':len(complete),
                'D_event_only':d_only,'baseline_event_only':b_only,
                'risk_difference_D_minus_baseline':(d_only-b_only)/len(complete) if complete else None,
                'retention_eligible_pairs':len(eligible),'mean_case_retention_difference':sum(diffs)/len(diffs) if diffs else None,
                'mean_completed_pair_retention_difference':sum(complete_diffs)/len(complete_diffs) if complete_diffs else None,
                'inferential_test':'NOT_APPLIED_shared_source_dependence'})
    return pairs


def main(run_path, output_path):
    verify_amendment()
    run=Path(run_path); dest=Path(output_path)
    verify_manifest(run)
    dest.mkdir(exist_ok=False)
    manifest=[json.loads(x) for x in (OUT/'E2_CASE_MANIFEST.jsonl').read_text().splitlines()]
    ledger={r['source_case']:r for r in read(EXPORT/'local_only/CASE_TRANSFER_LEDGER.json')}
    opportunities=defaultdict(list)
    for o in read(OUT/'E2_SUPPORTED_OPPORTUNITIES.json'): opportunities[o['case_id']].append(o)
    records=[]; scores=[]; missing=[]
    for m in manifest:
        case=m['case_id']; packet=read(EXPORT/ledger[case]['packet_file'])
        for arm in 'ABCD':
            slot=run/f'{case}_{arm}'; file=slot/'RESPONSE.json'
            if file.exists():
                verify_manifest(slot); rec=read(file)
                assert read(slot/'REPORTER_VISIBLE_PACKET.json')==packet
                if arm in 'AB' and (slot/'REQUEST.json').exists():
                    assert read(slot/'REQUEST.json')==read(AMENDMENT/'requests'/f"{ledger[case]['export_case']}_{arm}.json")
            else:
                rec={'case_id':case,'arm':arm,'status':'INCOMPLETE_RESERVED' if slot.exists() else 'NOT_EXECUTED','text':'','api_calls':int((slot/'API_ATTEMPT_RESERVED.json').exists()),'retries':0}
            rec['family']=m['family']; records.append(rec)
            s=score(rec,packet,opportunities[case]); s['family']=m['family']; scores.append(s)
            if rec['status']!='SUCCESS': missing.append({k:rec.get(k) for k in ['case_id','family','arm','status','api_error_code','error_type']})
    assert len(records)==408
    aggregates=[aggregate(scores,f,a) for f in ['F1','F2','F3','F4'] for a in 'ABCD']
    independent=verify_aggregation_independently(scores,aggregates)
    pairs=paired(scores,manifest)
    # Independent arithmetic for paired risk and retention (different iteration).
    by={(s['case_id'],s['arm']):s for s in scores}
    for p in pairs:
        ds=[s for s in scores if s['arm']=='D' and s['family']==p['family']]
        bs=[by[s['case_id'],p['comparison'][-1]] for s in ds]
        joint=[(d,b) for d,b in zip(ds,bs) if d['status']==b['status']=='SUCCESS']
        risk=sum(int(d['unsupported_screen_event'])-int(b['unsupported_screen_event']) for d,b in joint)/len(joint) if joint else None
        assert risk==p['risk_difference_D_minus_baseline']
        diffs=[d['retained']/d['opportunities']-b['retained']/b['opportunities'] for d,b in zip(ds,bs) if d['opportunities']]
        expected=sum(diffs)/len(diffs) if diffs else None
        assert expected is None if p['mean_case_retention_difference'] is None else abs(expected-p['mean_case_retention_difference'])<1e-12
    textfile(dest/'RESPONSES.jsonl',''.join(encode(r)+'\n' for r in records))
    textfile(dest/'PROVISIONAL_SCORES.jsonl',''.join(encode(s)+'\n' for s in scores))
    status='E2_PARTIAL' if missing else 'E2_EXECUTION_COMPLETE_E4_PENDING'
    write(dest/'METRICS.json',{'status':status,'interpretation':'PROVISIONAL_SCREEN_ONLY_E4_PENDING','families':aggregates,'pairs':pairs})
    write(dest/'INDEPENDENT_METRIC_VERIFICATION.json',{'aggregation':independent,'paired_arithmetic':'PASS'})
    write(dest/'FAILURES_AND_MISSINGNESS.json',missing)
    write(dest/'REAL_TARGET_OUTCOMES.json',[{k:s[k] for k in ['case_id','arm','status','opportunities','retained','partial','refused','omitted','unresolved','unsupported_screen_event']} for s in scores if s['family']=='F4'])
    generation={'time':now(),'status':status,'planned_contexts':102,'planned_slots':408,
        'statuses':dict(Counter(r['status'] for r in records)),'api_attempts':sum(r['api_calls'] for r in records),
        'retries':sum(r['retries'] for r in records),'new_scientific_fits':0,
        'requested_model':'gemini-3.6-flash','returned_models':sorted({r['actual_backend'] for r in records if r.get('actual_backend')}),
        'execution_manifest_sha256':sha(run/'SHA256_MANIFEST.json'),'protocol_sha256':sha(AMENDMENT/'E2_MODEL_AMENDMENT_V1.md'),
        'amendment_lock_sha256':sha(AMENDMENT/'AMENDMENT_LOCK.json'),
        'known_usage_estimated_usd':sum(r.get('estimated_usd') or 0 for r in records),
        'unknown_cost_attempts':sum(r['api_calls'] and r.get('estimated_usd') is None for r in records),'invoice_usd':None,
        'all_attempted_input_parity':'PASS','E4':'PENDING_NOT_STARTED'}
    write(dest/'GENERATION_SUMMARY.json',generation)
    lines=['# E2 Gemini3.6 Flash final report',f'\nStatus: **{status}**. Independent E4: **PENDING**.',
        '\nProspective model amendment and privacy-minimized reporting interface. Not an evaluation of Gemini3.5 Flash; not retroactive validation of the E1 interface.',
        f"\n102 cases /408 slots; statuses {generation['statuses']}; {generation['api_attempts']} API attempts; zero retries/new fits. Actual backends: {generation['returned_models']}.",
        '\n## Registered family-separated provisional metrics',
        '\n|Family|Arm|Completed/planned|Screen events/completed|Retained/opportunities|Refused|Partial|',
        '|---|---|---:|---:|---:|---:|---:|']
    for a in aggregates:lines.append(f"|{a['family']}|{a['arm']}|{a['completed']}/{a['planned']}|{a['provisional_screen_events']}/{a['completed']}|{a['retained_provisional']}/{a['conditional_numerical_opportunities']}|{a['refused']}|{a['partial']}|")
    lines += ['\nF1:TMS78; F2:OneK1K null10; F3:engineered5; F4:CRISPRi9. Undefined retention is not perfect utility. All failures remain in fixed denominators; bounds and paired contrasts are in METRICS.json.',
        '\n## Limitations',
        '\nThese are unchanged limited machine screens and conditional numerical opportunities, not expert-confirmed safety, biological ground truth or superiority. E4 semantic adjudication remains pending; no E4 experiment was run. Dependent source contexts preclude simple independent-case significance claims. TMS lacks retained per-gene effect tables; OneK1K uses source previews; E1 calibration warnings remain. Privacy aliases hide original adjustment names equally across arms. C/D are deterministic and not output-budget matched to A/B. No results are pooled across backend versions.',
        f"\nKnown token-cost estimate: ${generation['known_usage_estimated_usd']:.6f}; unknown-cost attempts: {generation['unknown_cost_attempts']}; not an invoice. Runtime stop reason: {read(run/'SUMMARY.json')['reason']}.",
        '\nSources: TMS https://doi.org/10.6084/m9.figshare.12654728.v1 (MIT); OneK1K https://doi.org/10.5281/zenodo.18870747 (CC BY4.0); CD4 Perturb-seq https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE314342 and https://virtualcellmodels.cziscience.com/dataset/genome-scale-tcell-perturb-seq (dataset card MIT). Source authors/complete citations remain in the original frozen source manifests. Summaries/selected evidence derived for the reporting evaluation; originals unchanged.',
        '\nPreservation and metrics independently checked. No additional biological validity is established. No E3/E4 execution or prior experiment rerun.']
    textfile(dest/'E2_FINAL_REPORT.md','\n'.join(lines)+'\n')
    write(dest/'PRESERVATION_AFTER.json',verify_amendment())
    print('analysis_manifest_sha256='+seal(dest))

if __name__=='__main__':main(sys.argv[1],sys.argv[2])
