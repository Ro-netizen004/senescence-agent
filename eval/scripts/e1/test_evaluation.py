import unittest
from score_reports import summarize
from verify_results import bh
import numpy as np

class EvaluationTests(unittest.TestCase):
    def test_empty_denominator_is_undefined(self):
        self.assertIsNone(summarize([])["retention"])

    def test_unresolved_stays_in_intended_denominator(self):
        records=[{"classification":s} for s in ["RETAINED","FALSE_REFUSAL","OMISSION","UNRESOLVED_INPUT_ACCESS"]]
        result=summarize(records)
        self.assertEqual(result["retention"],.25)
        self.assertEqual(result["false_refusal_rate"],.25)
        self.assertEqual(result["unresolved"],1)

    def test_bh_independent_arithmetic(self):
        np.testing.assert_allclose(bh([.001]+[1.]*8),[.009]+[1.]*8)
        np.testing.assert_allclose(bh([.04,.01,.03]),[.04,.03,.04])

if __name__=="__main__":unittest.main()
