import unittest
import numpy as np
import pandas as pd
from metrics import paired_effect_status,cpm_effects,bh,median_log_ratio_factors,warning_class

class FollowupTests(unittest.TestCase):
    def test_exact_half_retention_allowed(self):
        full=pd.Series([2.,-2.],index=["a","b"])
        omit=pd.DataFrame([[1.,-1.]]*4,columns=full.index)
        self.assertTrue(paired_effect_status(full,omit).paired_stable.all())

    def test_one_sign_reversal_fails_direction(self):
        full=pd.Series([2.],index=["a"]);omit=pd.DataFrame({"a":[2,2,2,-2]})
        self.assertFalse(paired_effect_status(full,omit).direction_stable.iloc[0])

    def test_missing_omission_is_not_zero_or_stable(self):
        full=pd.Series([2.],index=["a"]);omit=pd.DataFrame({"a":[2,2,np.nan,2]})
        self.assertFalse(paired_effect_status(full,omit).paired_stable.iloc[0])

    def test_zero_full_effect_cannot_be_robust(self):
        full=pd.Series([0.],index=["a"]);omit=pd.DataFrame({"a":[0,0,0,0]})
        self.assertFalse(paired_effect_status(full,omit).paired_stable.iloc[0])

    def test_omission_units_are_distinct(self):
        m=pd.DataFrame({"donor_id":["a","a","b","b","c","c","d","d"],"perturbation":["NTC","targeting"]*4})
        c=pd.DataFrame({"gene":[10,20,20,50,40,60,70,150],"background":[100]*8})
        f,single=cpm_effects(c,m,["gene"],False);g,paired=cpm_effects(c,m,["gene"],True)
        self.assertEqual(len(single),8);self.assertEqual(len(paired),4)
        pd.testing.assert_series_equal(f,g)
        self.assertFalse(np.isclose(single.iloc[0,0],paired.iloc[0,0]))

    def test_bh_and_normalization(self):
        np.testing.assert_allclose(bh([.001]+[1.]*8),[.009]+[1.]*8)
        sf,n=median_log_ratio_factors(pd.DataFrame([[10,20,0],[20,40,2]]))
        self.assertEqual(n,2);self.assertAlmostEqual(sf.iloc[1]/sf.iloc[0],2)

    def test_warnings_not_proof_of_correctness_or_invalidity(self):
        self.assertEqual(warning_class("residual degrees of freedom"),"EXPECTED_BUT_IMPORTANT_STATISTICAL_LIMITATION")
        self.assertEqual(warning_class("overflow encountered in matmul"),"UNRESOLVED_WITHOUT_ADDITIONAL_NUMERICAL_EVIDENCE")

if __name__=="__main__":unittest.main()
