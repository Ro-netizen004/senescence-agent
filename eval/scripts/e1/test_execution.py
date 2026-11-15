import unittest
import numpy as np
import pandas as pd
from execute_e1 import adapter,ARGS,independent_supported,paired_omission_masks
from agent.admissibility import check_admissibility
from agent.analysis_planner import validate_analysis_plan,apply_validated_plan
from agent.intent_router import RouteDecision
from tools.build_pseudobulk import build_pseudobulk_matrix
from statsmodels.stats.multitest import multipletests

class ExecutionTests(unittest.TestCase):
    def fixture(self):
        index=[f"D{d}__{a}" for d in range(4) for a in ["NTC","targeting"]]
        counts=pd.DataFrame(np.arange(24).reshape(8,3)+10,index=index,columns=["g1","g2","g3"])
        meta=pd.DataFrame({"donor_id":[f"D{d}" for d in range(4) for _ in range(2)],
                           "perturbation":["NTC","targeting"]*4,"n_cells":[20,21]*4},index=index)
        return counts,meta

    def test_adapter_preserves_actual_cell_counts_raw_sums_and_gate(self):
        counts,meta=self.fixture();data=adapter(counts,meta)
        self.assertEqual(data.n_obs,int(meta.n_cells.sum()))
        got,gm=build_pseudobulk_matrix(data,"CD4 T cell",group_column="perturbation",covariates=["donor_id"])
        pd.testing.assert_frame_equal(got,counts)
        self.assertEqual(gm.attrs["sample_cell_counts"],meta.n_cells.to_dict())
        self.assertTrue(check_admissibility("run_deseq2",ARGS,data)["admissible"])
        self.assertEqual(gm.attrs["count_validation"]["source"],"layers[counts]")

    def test_low_cell_count_cannot_be_fabricated(self):
        c,m=self.fixture();m.iloc[0,m.columns.get_loc("n_cells")]=19
        with self.assertRaises(ValueError):adapter(c,m)

    def test_pair_omissions_remove_both_arms(self):
        c,m=self.fixture();masks=paired_omission_masks(m)
        self.assertEqual(len(masks),4)
        for donor,keep in masks.items():
            self.assertEqual(int(keep.sum()),6)
            self.assertNotIn(donor,m.loc[keep,"donor_id"].tolist())
            self.assertEqual(m.loc[keep].groupby("donor_id").size().tolist(),[2,2,2])

    def test_planner_cannot_change_contrast_or_donor_pairing(self):
        c,m=self.fixture();data=adapter(c,m)
        route=RouteDecision(workflow_id="deseq2",tool_args={"run_deseq2":ARGS.copy()})
        proposal=dict(method="pseudobulk_deseq2",cell_type="CD4 T cell",unit_of_replication="sample_id",
                      group_column="perturbation",reference_group="targeting",comparison_group="NTC",covariates=[])
        audit=validate_analysis_plan(proposal,data,route)
        self.assertEqual(audit["status"],"corrected_to_deterministic")
        self.assertEqual(apply_validated_plan(route,audit).tool_args["run_deseq2"],ARGS)

    def test_independent_support_requires_uncertainty_and_adjustment(self):
        frame=pd.DataFrame({"log2FoldChange":[1,-1,1,np.nan,1,1],"lfcSE":[.1,.1,1,.1,-1,.1],
                            "padj":[.01,.01,.01,.01,.01,.05]})
        self.assertEqual(independent_supported(frame,"padj").tolist(),[True,True,False,False,False,False])

    def test_support_has_no_fold_change_cutoff_or_gate_dependency(self):
        frame=pd.DataFrame({"log2FoldChange":[.1],"lfcSE":[.01],"padj":[.01]})
        self.assertTrue(independent_supported(frame,"padj").iloc[0])
        frame["gate2"]="withheld"
        self.assertTrue(independent_supported(frame,"padj").iloc[0])

    def test_nine_hypothesis_denominator_includes_missing(self):
        q=multipletests([.001]+[1.]*8,method="fdr_bh")[1]
        self.assertAlmostEqual(q[0],.009)
        self.assertTrue((q[1:]==1).all())

if __name__=="__main__":unittest.main()
