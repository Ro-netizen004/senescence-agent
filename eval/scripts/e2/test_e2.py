import copy
import unittest
from common import OUT,read,digest
from prepare import diagnostic_facts,supported_rows
from reporters import template,firewall,MODEL_CONFIG
from scoring import score,numerical_match

def fixture():
    return {'case_id':'SYNTHETIC_ONLY','dataset':'dummy','cell_type':'test','biological_condition':'dummy condition',
        'design':{'formula':'~ donor + condition','n_samples':8,'donors_by_group':{'control':4,'treated':4}},
        'perturbation_identity':{'symbol':'DUMMY','gene_id':'TEST000'},
        'statistics':{'contrast':'treated versus control','n_significant_fdr_0_05':1,
            'rows':[{'gene':'TEST000','symbol':'DUMMY','log2FoldChange':-2.,'lfcSE':.2,'padj':.001}],
            'missingness':'dummy','on_target_family_A':None},
        'numerical_warnings':[],'warning_scope':'dummy','limitations':['Only four donors. Numerical uncertainty remains.'],
        'paired_donor_sensitivity':{'status':'UNAVAILABLE'}}

def private(p,verdict='ok'):
    return {'tool':{'results':p['statistics']['rows'],'n_significant_fdr_0_05':1,'n_samples':8,
        'samples_per_group':{'control':4,'treated':4},'reference_group':'control','comparison_group':'treated',
        'result_plausibility':{'verdict':verdict,'reasons':[]},'replicate_stability':{'verdict':'stable'}},
        'args':{'cell_type':'test'},'gate1_mode':'synthetic-only fixture'}

class Tests(unittest.TestCase):
    def test_c_has_numbers_and_metadata(self):
        t=template(fixture());self.assertIn('TEST000',t);self.assertIn('donor',t);self.assertIn('uncertainty',t)
    def test_d_original_body_preserved(self):
        p=fixture();t,a=firewall(p,private(p));self.assertTrue(t.startswith(a['original_rendered_body']))
    def test_d_pass_supplement(self):
        p=fixture();t,a=firewall(p,private(p));self.assertIn('| TEST000 (DUMMY) | -2 | 0.2 | 0.001 |',t)
    def test_d_withholding_not_bypassed(self):
        p=fixture();t,a=firewall(p,private(p,'suspect'));self.assertTrue(a['original_schema']['result_withheld'])
        self.assertNotIn('| TEST000',t);self.assertNotIn('0.001',t);self.assertNotIn('TEST000',t)
    def test_d_blocked_no_supplement(self):
        p=fixture();d=private(p);d['tool']['admissibility']={'admissible':False,'blocked_reasons':['test:block'],'checks':{}}
        d['tool']['error']='inadmissible_inference'
        t,a=firewall(p,d);self.assertNotIn('TEST000',t);self.assertNotIn('0.001',t)
    def test_sensitivity_cannot_change_license(self):
        p=fixture();d=private(p,'suspect');a=firewall(p,d)[1]['inference_state']
        p['paired_donor_sensitivity']={'all_effects_perfect':True}
        self.assertEqual(a,firewall(p,d)[1]['inference_state'])
    def test_warning_preservation(self):
        p=fixture();p['numerical_warnings']=[{'text':'SYNTHETIC_WARNING','count':3}]
        self.assertIn('SYNTHETIC_WARNING',template(p));self.assertIn('SYNTHETIC_WARNING',firewall(p,private(p))[0])
    def test_no_packet_mutation(self):
        p=fixture();h=digest(p);template(p);firewall(p,private(p));self.assertEqual(h,digest(p))
    def test_opportunity_independent_of_gate(self):
        p=fixture();a=supported_rows(p);p['governance']={'deny':True};self.assertEqual(a,supported_rows(p))
    def test_nonfinite_not_opportunity(self):
        p=fixture();p['statistics']['rows'][0]['lfcSE']=None;self.assertEqual([],supported_rows(p))
    def test_license_removed(self):self.assertEqual(diagnostic_facts({'verdict':'suspect','n':2,'reasons':['bad']}),{'n':2})
    def test_matching_rounding(self):self.assertTrue(numerical_match(['| X | -2 | .2 | .001 |'],-2,.001))
    def test_wrong_value(self):self.assertFalse(numerical_match(['| X | 2 | .2 | .001 |'],-2,.001))
    def test_failed_not_safe_response(self):
        s=score({'status':'API_FAILURE','case_id':'x','arm':'A'},fixture(),[]);self.assertIsNone(s['unsupported_screen_event'])
    def test_retained_with_qualifications(self):
        p=fixture();o={'id':'x','gene':'TEST000','symbol':'DUMMY','log2FC':-2,'padj':.001}
        s=score({'status':'SUCCESS','text':template(p),'case_id':'x','arm':'C'},p,[o]);self.assertEqual(s['retained'],1)
    def test_failure_denominator(self):
        o={'id':'x','gene':'TEST000','log2FC':-2,'padj':.001}
        s=score({'status':'API_FAILURE','case_id':'x','arm':'A'},fixture(),[o]);self.assertEqual(s['execution_failed_opportunities'],1)
    def test_real_manifest_no_generation(self):
        import json
        rows=[json.loads(l) for l in (OUT/'E2_CASE_MANIFEST.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows),102);self.assertEqual(len({r['case_id'] for r in rows}),102)
        for r in rows:
            p=read(OUT/'packets'/f'{r["case_id"]}.json');self.assertNotIn('inference_state',p)
            self.assertNotIn('gold',p);self.assertNotIn('reply',p)
    def test_mapping(self):
        for p in (OUT/'packets').glob('F4_*.json'):
            r=read(p);self.assertEqual(r['perturbation_identity']['symbol'],p.stem[3:])
    def test_sample_frame(self):self.assertEqual(len(set(read(OUT/'E2_E4_SAMPLE.json')['contexts'])),40)
    def test_recursive_label_exclusion(self):
        from validate import keys,FORBIDDEN
        for p in (OUT/'packets').glob('*.json'):self.assertFalse(FORBIDDEN & set(keys(read(p))))
    def test_all_policy_states_unchanged(self):
        from validate import validate
        self.assertEqual(len(validate()),102)
    def test_common_numeric_rows(self):
        for p in (OUT/'packets').glob('*.json'):
            self.assertEqual(read(p)['statistics']['rows'],read(OUT/'arm_d_inputs'/p.name)['tool']['results'])
    def test_all_mapping_rows_present(self):
        for p in (OUT/'packets').glob('F4_*.json'):
            r=read(p);identity=r['perturbation_identity'];rows=r['statistics']['rows']
            self.assertEqual([x['symbol'] for x in rows if x['gene']==identity['gene_id']],[identity['symbol']])

if __name__=='__main__':unittest.main()
