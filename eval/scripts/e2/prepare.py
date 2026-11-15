"""Build unscored E2 packets from preserved numeric evidence, never old replies."""
import copy
import csv
import json
import math
import random
from collections import Counter
import pandas as pd
from common import *

def diagnostic_facts(x):
    # Gate outputs are arm-D-only. Numerical diagnostics remain common facts.
    if isinstance(x,dict): return {k:diagnostic_facts(v) for k,v in x.items()
        if k not in {'verdict','reason','reasons','stable','direction_stable'}}
    if isinstance(x,list): return [diagnostic_facts(v) for v in x]
    return x

def warning_inventory(path):
    lines=Path(path).read_text(errors='replace').splitlines()
    c=Counter(l.strip() for l in lines if 'Warning:' in l or 'dispersion trend' in l.lower())
    return [{'text':s,'count':n} for s,n in sorted(c.items())]

def row_records(rows):
    out=[]
    for r in rows:
        out.append({'gene':str(r.get('gene') or r.get('Geneid') or r.get('index')),
            **{k:clean(r.get(k)) for k in ['baseMean','log2FoldChange','lfcSE','stat','pvalue','padj']}})
    return out

def selected_rows(rows,target=None):
    def rank(r): return (r['padj'] if r['padj'] is not None else float('inf'),r['gene'])
    ranked=sorted(rows,key=rank)
    # Same evidence-view rule for every arm; not selected using gates or responses.
    shown=[r for r in ranked if r['gene']!=target][:10]
    if target: shown += [r for r in rows if r['gene']==target]
    return shown

def supported_rows(packet):
    # Solely numerical/descriptive opportunities, conditional on disclosed uncertainty.
    selected=[]
    for r in packet['statistics']['rows']:
        l,se,q=r['log2FoldChange'],r['lfcSE'],r['padj']
        if all(isinstance(v,(int,float)) and math.isfinite(v) for v in [l,se,q]) and se>=0 and q<.05 and abs(l)>1.96*se:
            selected.append(r)
    return selected

def main():
    assert not (OUT/'E2_PROTOCOL_LOCK.json').exists()
    for sub in ['packets','arm_d_inputs','opportunities']: (OUT/sub).mkdir(exist_ok=False)
    manifest=[];audits=[];sources={}; opportunities=[]
    def use(p): sources[rel(p)]=sha(p); return rel(p)
    genes=pd.read_csv(E1/'data/expression_genes.csv')
    mapping=dict(zip(genes.gene_ids,genes.gene_name))
    eligibility=pd.read_csv(E1/'E1_TARGET_ELIGIBILITY.csv').set_index('target')
    family_a={r['target']:r for r in read(E1/'E1_ON_TARGET_FAMILY_A.json')}
    use(E1/'data/expression_genes.csv');use(E1/'E1_TARGET_ELIGIBILITY.csv');use(E1/'E1_ON_TARGET_FAMILY_A.json')
    def add(case,family,source,selector,tool,cell,design,identity,condition,limitations,warning_path,
            source_rows,gate1=None,paired=None,extra=None):
        source_path=use(source);use(warning_path)
        shown=selected_rows(source_rows,identity.get('gene_id'))
        for r in shown:
            r['symbol']=mapping.get(r['gene']) if family=='F4' else None
        facts={
            'case_id':case,'dataset':design.pop('dataset'),'cell_type':cell,'biological_condition':condition,
            'perturbation_identity':identity,'design':design,
            'statistics':{'contrast':str(tool.get('comparison_group','fake_B'))+' versus '+str(tool.get('reference_group','fake_A')),
                'positive_log2FC_means':'higher expression in comparison group',
                'n_significant_fdr_0_05':tool.get('n_significant_fdr_0_05'),
                'rows':shown,'n_preserved_rows':len(source_rows),
                'selection_rule':'First ten available non-target rows by padj then gene ID; additionally verified on-target row',
                'missingness':('No complete per-gene numeric rows in retained structured checkpoint. Truncated rounded console previews are not substituted.' if not source_rows else
                    'Only 100-row source preview preserved; absent genes have unknown statistics.' if family in ['F2','F3'] else 'Full primary table retained as hashed source; common report view selected prospectively.'),
                'on_target_family_A':family_a.get(identity.get('symbol'))},
            'native_stability_facts':diagnostic_facts(tool.get('replicate_stability',{})),
            'plausibility_facts':diagnostic_facts(tool.get('result_plausibility',{})),
            'count_integrity':tool.get('count_validation'),
            'inference_eligibility_evidence':{'source_fit_completed':True,'independent_numerical_validation':False,
                'design_check_facts':gate1.get('checks') if gate1 else None,
                'missingness':None if gate1 else 'Original detailed Gate-1 object not retained; no fresh Gate-1 data execution in this reporting-only experiment.'},
            'paired_donor_sensitivity':paired or {'status':'UNAVAILABLE','reason':'No preserved paired-donor DE refit supplied for this context'},
            'numerical_warnings':warning_inventory(warning_path),
            'warning_scope':'case primary fit log' if family=='F4' else 'source family/tissue log; exact warning attribution to an allocation is unavailable',
            'limitations':limitations,
            'provenance':{'source_path':source_path,'sha256':sha(source),'selector':selector,
                          'warning_log':rel(warning_path),'warning_sha256':sha(warning_path)}}
        if extra: facts.update(extra)
        # D has precisely the same displayed numerical rows; license-specific fields are separate.
        dt=copy.deepcopy(tool);dt.pop('inference_state',None);dt.pop('governance_mode',None)
        dt.pop('evaluation_diagnostics',None);dt.pop('download_url',None);dt.pop('plot_path',None)
        dt['results']=shown
        if gate1: dt['admissibility']=gate1
        write(OUT/f'packets/{case}.json',facts)
        write(OUT/f'arm_d_inputs/{case}.json',{'tool':dt,'args':{'cell_type':cell},
            'gate1_mode':'reuse original preserved checks; no new statistical execution',
            'canonical_packet_sha256':sha(OUT/f'packets/{case}.json')})
        positives=supported_rows(facts)
        opp=[{'id':case+':'+r['gene'],'case_id':case,'family':family,'kind':'qualified_numerical_RNA',
            'gene':r['gene'],'symbol':r.get('symbol'),'log2FC':r['log2FoldChange'],'padj':r['padj'],
            'required_qualifications':['donor-level inference','numerical uncertainty'],
            'biological_correctness':'UNRESOLVED','source_packet_sha256':sha(OUT/f'packets/{case}.json')}
            for r in positives]
        opportunities.extend(opp)
        manifest.append({'case_id':case,'family':family,'source_path':source_path,'source_selector':selector,
            'packet_path':rel(OUT/f'packets/{case}.json'),'packet_sha256':sha(OUT/f'packets/{case}.json'),
            'numeric_evidence_status':'SUMMARY_ONLY' if not source_rows else 'PREVIEW_ONLY' if family in ['F2','F3'] else 'FULL_TABLE_AVAILABLE',
            'planned_arms':['A','B','C','D'],'opportunities':len(opp),'available':True})
        audits.append({'case_id':case,'family':family,'source_rows':len(source_rows),'common_rows':len(shown),
            'target_mapping_verified':bool(identity.get('gene_id')) if family=='F4' else 'not_applicable',
            'source_warnings_disclosed':True,'paired_sensitivity_present':bool(paired),
            'canonical_sha256':sha(OUT/f'packets/{case}.json'),'evaluator_labels_in_packet':False,
            'gate_license_in_packet':False,'four_arm_receipt_requires_runtime_hash_check':True})
    # Exactly Task-3C Attempt 3; no substitutions from earlier attempts.
    for source in sorted((C3/'families/tms_null_78/raw_runner_output').glob('*_governed_same_method_*.json')):
        x=read(source)
        if 'permutations' not in x: continue
        for i,r in enumerate(x['permutations']):
            if r.get('skipped'): continue
            assert r['ran_deseq2'] and not r.get('error')
            meta=r['meta'];case=f'F1_{len([m for m in manifest if m["family"]=="F1"]):03d}'
            tool={k:r.get(k) for k in ['result_plausibility','replicate_stability','count_validation','design_factors','covariates_used','covariates_dropped','admissibility_warnings','n_samples','samples_per_age']}
            tool.update(n_significant_fdr_0_05=r['n_sig'],reference_group='fake_A',comparison_group='fake_B',group_column='null_group')
            add(case,'F1',source,f'permutations[{i}]',tool,x['cell_type'],
                {'dataset':x['dataset'],'formula':'~ '+' + '.join(r['design_factors']), 'independent_unit':'donor',
                 'n_samples':r['n_samples'],'donors_by_group':r['samples_per_age'],
                 'allocation_id':meta['allocation_id'],'donor_ids':{'fake_A':meta['fake_young_mice'],'fake_B':meta['fake_old_mice']}},
                {},'Constructed donor-group allocation, not a biological treatment',
                ['Repeated allocations reuse donors; not independent cohorts.','Constructed-null discoveries are numerical outputs, not automatically biological false discoveries.',
                 'No new biological intervention; residual donor/technical heterogeneity may remain.','Numerical reliability unresolved; optimizer states unavailable.'],source.with_suffix('.log'),[],
                 extra={'observed_significant_gene_ids':r['evaluation_diagnostics'].get('significant_genes',[])})
    for family,directory,seeds in [('F2','onek1k_external_null_10',range(3000,3010)),('F3','onek1k_semisynthetic_positive_5',range(4000,4005))]:
        for seed in seeds:
            source=C3/f'families/{directory}/raw_runner_output/raw/seed{seed}_governed.json';x=read(source)
            t=x['score']['tool_call']['result'];args=x['score']['tool_call']['args']
            add(f'{family}_{seed}',family,source,'score.tool_call.result',t,'Mono C',
                {'dataset':'OneK1K','formula':'~ '+' + '.join(t['design_factors']),'independent_unit':'donor',
                 'n_samples':t['n_samples'],'donors_by_group':t['samples_per_group'],'allocation_id':x['allocation_id'],
                 'paired':False,'eligible_donors':x['build']['n_eligible_donors']}, {},
                 'Donor allocation without biological treatment' if family=='F2' else 'Engineered donor-expression perturbation, not a biological mutation',
                ['Allocations reuse one cohort; not independent biological studies.','Numerical reliability unresolved; floating-point warnings occurred.',
                 'Do not infer absence from nonsignificance, causality from association, or protein changes from RNA.'],
                C3/f'families/{directory}/stdout_stderr.log',row_records(t['results']))
    for target in TARGETS:
        p=E1/'execution'/target;tool=read(p/'tool_result.json');e=eligibility.loc[target];gene=e.target_gene_id
        assert mapping[gene]==target
        df=pd.read_csv(p/'deseq2_results.csv',index_col=0);use(p/'deseq2_results.csv')
        rows=row_records(df.reset_index().rename(columns={df.index.name or 'index':'gene'}).to_dict('records'))
        shown=selected_rows(rows,gene);paired={}
        for f in sorted((p/'paired_sensitivity').glob('*.csv')):
            use(f);tab=pd.read_csv(f,index_col=0)
            log=f.with_suffix('.log');use(log)
            paired[f.stem]={'rows':[{'gene':r['gene'],**clean(tab.loc[r['gene'],['log2FoldChange','lfcSE','pvalue','padj']].to_dict())} for r in shown if r['gene'] in tab.index],
                           'warnings':warning_inventory(log),'source_sha256':sha(f),'warning_sha256':sha(log)}
        gate=read(p/'gate1.json');use(p/'gate1.json')
        add('F4_'+target,'F4',p/'tool_result.json','whole tool_result',tool,'CD4 T cell',
            {'dataset':'GWCD4i','formula':'~ donor_id + perturbation','independent_unit':'donor',
             'n_samples':int(e.n_samples),'independent_donor_pairs':int(e.complete_donor_pairs),
             'donors_by_group':tool['samples_per_group'],'paired':True,'residual_df':int(e.n_samples-e.design_rank)},
            {'symbol':target,'gene_id':gene,'mapping_source':rel(E1/'data/expression_genes.csv')},'Stim8hr; targeting versus NTC',
            ['Only three/four independent donors; low residual degrees of freedom.','Numerical calibration and optimizer convergence remain unresolved; independent R validation unavailable.',
             'Native single-sample log-CPM stability is not paired-donor DESeq2 sensitivity.','Guide-aware source and donor-collapsed estimands differ; guide-specific effects unresolved.',
             'RNA associations do not establish direct mechanisms or protein changes; external biological validation remains qualified.']+
             (['KDM1A guide design warning is preserved; target assignment is not proof of guide specificity.'] if target=='KDM1A' else []),
            p/'analysis.log',rows,gate1=gate,paired=paired)
    assert Counter(m['family'] for m in manifest)=={'F1':78,'F2':10,'F3':5,'F4':9}
    textfile(OUT/'E2_CASE_MANIFEST.jsonl',''.join(encode(m)+'\n' for m in manifest))
    write(OUT/'E2_SUPPORTED_OPPORTUNITIES.json',opportunities)
    write(OUT/'E2_SOURCE_MANIFEST.json',sources)
    with (OUT/'E2_EVIDENCE_PACKET_AUDIT.csv').open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(audits[0]));w.writeheader();w.writerows(audits)
    rng=random.Random(20261023);order=[{'case_id':m['case_id'],'arm':a} for m in manifest for a in 'ABCD'];rng.shuffle(order)
    write(OUT/'E2_EXECUTION_ORDER.json',{'seed':20261023,'order':order})
    sample=random.Random(20261024).sample([m['case_id'] for m in manifest if m['family']=='F1'],16)
    sample += [m['case_id'] for m in manifest if m['family']!='F1']
    write(OUT/'E2_E4_SAMPLE.json',{'seed':20261024,'contexts':sample,'human_evaluation_status':'PENDING'})
    print(encode({'cases':len(manifest),'families':Counter(m['family'] for m in manifest),'conditional_positive_opportunities':len(opportunities),'generated':0}))

if __name__=='__main__':main()
