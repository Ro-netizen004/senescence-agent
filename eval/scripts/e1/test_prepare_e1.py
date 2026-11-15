import unittest
import numpy as np
import pandas as pd
from scipy import sparse
from prepare_e1 import aggregate,technical_mask,validate_counts,mapping_matches

class PreparationTests(unittest.TestCase):
    def test_ntc_blank_gene_id_is_explicit_not_a_target_wildcard(self):
        row=pd.Series(dict(guide_type="non-targeting",perturbed_gene_name="NTC",perturbed_gene_id="NTC"))
        source=pd.Series(dict(perturbed_gene_name="NTC",perturbed_gene_id=np.nan))
        self.assertTrue(mapping_matches(row,source))
        row.guide_type="targeting"
        self.assertFalse(mapping_matches(row,source))
        row.perturbed_gene_name="X"
        self.assertFalse(mapping_matches(row,source))

    def test_no_eligible_pairs_preserves_empty_shape_and_coverage(self):
        X,obs=self.fixture()
        obs.n_cells=1
        counts,meta,coverage=aggregate(X,obs,"X",0)
        self.assertEqual(counts.shape,(0,2))
        self.assertEqual(len(meta),0)
        self.assertEqual(len(coverage),4)

    def fixture(self):
        rows=[]
        for donor in ["a","b","c","d"]:
            for target,kind in [("X","targeting"),("NTC","non-targeting")]:
                for guide in [1,2]:
                    rows.append(dict(donor_id=donor,perturbed_gene_name=target,guide_type=kind,
                                     guide_id=f"{target}-{guide}",n_cells=10,total_counts=30,
                                     **{"10xrun_id":"batch"},keep_effective_guides=False,keep_for_DE=False))
        return sparse.csr_matrix(np.tile([10,20],(16,1))),pd.DataFrame(rows)

    def test_sum_guides_preserves_donors_and_counts(self):
        X,obs=self.fixture()
        counts,meta,coverage=aggregate(X,obs,"X",0)
        self.assertEqual(counts.shape,(8,2))
        np.testing.assert_array_equal(counts,np.tile([20,40],(8,1)))
        self.assertEqual(meta.groupby("donor_id").size().tolist(),[2,2,2,2])
        self.assertTrue(all(r["complete_pair"] for r in coverage))

    def test_underpowered_donor_removed_as_pair(self):
        X,obs=self.fixture()
        obs.loc[0,"n_cells"]=4
        counts,meta,coverage=aggregate(X,obs,"X",0)
        self.assertEqual(len(meta),6)
        self.assertNotIn("a",meta.donor_id.tolist())

    def test_efficacy_flags_do_not_filter(self):
        _,obs=self.fixture()
        self.assertTrue(technical_mask(obs,0).all())

    def test_count_validation_rejects_fraction_negative_nan(self):
        for bad in [0.5,-1,np.nan,np.inf]:
            with self.assertRaises(ValueError):
                validate_counts(sparse.csr_matrix([[bad,1]]))

    def test_batch_mismatch_removes_pair(self):
        X,obs=self.fixture()
        obs.loc[[0,1],"10xrun_id"]="other"
        _,meta,_=aggregate(X,obs,"X",0)
        self.assertEqual(len(meta),6)

if __name__ == "__main__":
    unittest.main()
