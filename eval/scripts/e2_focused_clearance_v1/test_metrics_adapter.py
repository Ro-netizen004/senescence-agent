import unittest
from finalize_amended import paired
from finalize import aggregate, verify_aggregation_independently
from scoring import score
from test_e2 import fixture


class MetricAdapterTests(unittest.TestCase):
    def records(self):
        manifest=[{'case_id':'SYNTHETIC_'+f,'family':f} for f in ('F1','F2','F3','F4')]
        scores=[]
        for m in manifest:
            for a in 'ABCD':
                r={'case_id':m['case_id'],'arm':a,'status':'SUCCESS','text':'Synthetic empty report'}
                s=score(r,fixture(),[]);s['family']=m['family'];scores.append(s)
        return manifest,scores

    def test_zero_opportunities_undefined_retention(self):
        m,s=self.records()
        for p in paired(s,m):self.assertIsNone(p['mean_case_retention_difference'])
        a=[aggregate(s,f,arm) for f in ('F1','F2','F3','F4') for arm in 'ABCD']
        self.assertTrue(all(x['retention_intention_to_report'] is None for x in a))
        self.assertEqual(verify_aggregation_independently(s,a)['status'],'PASS')

    def test_fixed_failure_denominator(self):
        m,s=self.records()
        s[0]=score({'case_id':m[0]['case_id'],'arm':'A','status':'API_FAILURE','text':''},fixture(),[])
        s[0]['family']='F1'
        a=aggregate(s,'F1','A')
        self.assertEqual(a['planned'],1);self.assertEqual(a['completed'],0)
        self.assertEqual(a['screen_failure_bound_low'],0)
        self.assertEqual(a['screen_failure_bound_high'],1)

    def test_direction_of_paired_risk_difference(self):
        m,s=self.records();s[3]['unsupported_screen_event']=True
        p=next(p for p in paired(s,m) if p['family']=='F1' and p['comparison']=='D-B')
        self.assertEqual(p['risk_difference_D_minus_baseline'],1)
        self.assertEqual(p['D_event_only'],1)

    def test_retention_failure_counts_zero(self):
        m,s=self.records()
        for r in s:
            r['opportunities']=2;r['retained']=1 if r['arm']=='D' else 0
        p=next(p for p in paired(s,m) if p['family']=='F1' and p['comparison']=='D-B')
        self.assertEqual(p['mean_case_retention_difference'],.5)

if __name__=='__main__':unittest.main()
