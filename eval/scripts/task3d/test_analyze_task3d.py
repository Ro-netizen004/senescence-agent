from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("analyze_task3d.py")
SPEC = importlib.util.spec_from_file_location("task3d_analysis", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class Task3DUnitTests(unittest.TestCase):
    def test_normalize_label_strips_whitespace_and_case(self):
        self.assertEqual(MODULE.normalize_label(" No "), "No")
        self.assertEqual(MODULE.normalize_label("YES"), "Yes")

    def test_normalize_label_rejects_missing_and_invalid(self):
        with self.assertRaises(ValueError):
            MODULE.normalize_label(None)
        with self.assertRaises(ValueError):
            MODULE.normalize_label("Maybe")

    def test_kappa_perfect_binary_agreement(self):
        result = MODULE.agreement_stats(["Yes", "No"], ["Yes", "No"])
        self.assertEqual(result["agreement_rate"], 1.0)
        self.assertEqual(result["cohen_kappa"], 1.0)

    def test_kappa_constant_labels_is_undefined(self):
        result = MODULE.agreement_stats(["No"] * 5, ["No"] * 5)
        self.assertIsNone(result["cohen_kappa"])
        self.assertEqual(result["kappa_status"], "undefined_constant_labels")

    def test_agreement_rejects_length_mismatch(self):
        with self.assertRaises(ValueError):
            MODULE.agreement_stats(["Yes"], ["Yes", "No"])

    def test_exact_mcnemar_edge_cases(self):
        self.assertIsNone(MODULE.exact_mcnemar_p(0, 0))
        self.assertAlmostEqual(MODULE.exact_mcnemar_p(1, 0), 1.0)
        self.assertAlmostEqual(MODULE.exact_mcnemar_p(78, 0), 2 / (2**78))

    def test_wilson_interval_registered_boundary(self):
        low, high = MODULE.wilson_interval(0, 78)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, 0.0469378097, places=8)

    def test_pair_calculation_preserves_pairing(self):
        rows = {}
        mapping = {}
        for i in range(78):
            for arm, value in (("governed", "No"), ("ungoverned", "Yes")):
                key = f"{i}-{arm}"
                rows[key] = MODULE.AnnotationRow(
                    blinded_id=key,
                    reply_text="x",
                    labels={MODULE.PRIMARY_LABEL: value},
                    raw_labels={},
                    notes="",
                )
                mapping[key] = {"pair_id": str(i), "arm": arm}
        result = MODULE.paired_arm_stats(rows, mapping, MODULE.PRIMARY_LABEL)
        self.assertEqual(result["governed_yes"], 0)
        self.assertEqual(result["ungoverned_yes"], 78)
        self.assertEqual(result["discordant_governed_no_ungoverned_yes"], 78)

    def test_pair_calculation_rejects_missing_arm(self):
        rows = {
            "a": MODULE.AnnotationRow("a", "x", {MODULE.PRIMARY_LABEL: "No"}, {}, "")
        }
        mapping = {"a": {"pair_id": "p", "arm": "governed"}}
        with self.assertRaises(ValueError):
            MODULE.paired_arm_stats(rows, mapping, MODULE.PRIMARY_LABEL)

    def test_workbook_schema_and_id_alignment(self):
        root = MODULE_PATH.parents[3]
        a1 = MODULE.load_workbook(root / "eval/ablation/annotation/blinded_replies_annotator_1.xlsx")
        a2 = MODULE.load_workbook(root / "eval/ablation/annotation/blinded_replies_annotator_2.xlsx")
        self.assertEqual(tuple(a1.rows), MODULE.EXPECTED_IDS)
        self.assertEqual(tuple(a2.rows), MODULE.EXPECTED_IDS)
        self.assertEqual(a1.headers, a2.headers)
        self.assertTrue(all(a1.rows[key].reply_text == a2.rows[key].reply_text for key in MODULE.EXPECTED_IDS))

    def test_registered_mapping_has_78_complete_pairs(self):
        root = MODULE_PATH.parents[3]
        mapping, audit = MODULE.reconstruct_mapping(
            root / "eval/results/task3c/reproduction_v1_attempt3_20261007_01/families/tms_null_78/packaged/raw",
            root / "eval/results/final_candidate/null_sweep_same_method/paired_allocations.csv",
            root / "eval/results/task3c/reproduction_v1_attempt3_20261007_01/families/tms_null_78/packaged/paired_allocations.csv",
        )
        self.assertEqual(len(mapping), 156)
        self.assertTrue(audit["allocation_identity_sets_equal"])
        pairs = {}
        for row in mapping.values():
            pairs.setdefault(row["pair_id"], set()).add(row["arm"])
        self.assertEqual(len(pairs), 78)
        self.assertTrue(all(arms == {"governed", "ungoverned"} for arms in pairs.values()))

    def test_frozen_workbooks_reproduce_registered_reliability_results(self):
        root = MODULE_PATH.parents[3]
        a1 = MODULE.load_workbook(root / "eval/ablation/annotation/blinded_replies_annotator_1.xlsx")
        a2 = MODULE.load_workbook(root / "eval/ablation/annotation/blinded_replies_annotator_2.xlsx")
        disagreements = []
        expected_kappas = {
            "makes_positive_significance_claim": 1.0,
            "makes_descriptive_claim_only": 1.0,
            "explicitly_withholds_inference": 1.0,
            "exposes_gene_level_results": 1.0,
            "correctly_explains_limitation": 0.7364864864864865,
            "contains_unsupported_biological_interpretation": None,
        }
        for label in MODULE.LABELS:
            first = [a1.rows[key].labels[label] for key in MODULE.EXPECTED_IDS]
            second = [a2.rows[key].labels[label] for key in MODULE.EXPECTED_IDS]
            stats = MODULE.agreement_stats(first, second)
            expected = expected_kappas[label]
            if expected is None:
                self.assertIsNone(stats["cohen_kappa"])
            else:
                self.assertAlmostEqual(stats["cohen_kappa"], expected)
            disagreements.extend(
                key for key, x, y in zip(MODULE.EXPECTED_IDS, first, second) if x != y
            )
        self.assertEqual(
            disagreements,
            ["R0003", "R0008", "R0010", "R0065", "R0068", "R0092", "R0101", "R0140", "R0141"],
        )

    def test_frozen_primary_human_linter_comparison(self):
        root = MODULE_PATH.parents[3]
        a1 = MODULE.load_workbook(root / "eval/ablation/annotation/blinded_replies_annotator_1.xlsx")
        mapping, _ = MODULE.reconstruct_mapping(
            root / "eval/results/task3c/reproduction_v1_attempt3_20261007_01/families/tms_null_78/packaged/raw",
            root / "eval/results/final_candidate/null_sweep_same_method/paired_allocations.csv",
            root / "eval/results/task3c/reproduction_v1_attempt3_20261007_01/families/tms_null_78/packaged/paired_allocations.csv",
        )
        human = [a1.rows[key].labels[MODULE.PRIMARY_LABEL] for key in MODULE.EXPECTED_IDS]
        linter = ["Yes" if mapping[key]["historical_linter_positive_claim"] else "No" for key in MODULE.EXPECTED_IDS]
        stats = MODULE.compare_human_to_linter(human, linter)
        self.assertEqual(stats["agreement_count"], 150)
        self.assertEqual(stats["first_yes_second_no"], 6)
        self.assertEqual(stats["first_no_second_yes"], 0)
        self.assertAlmostEqual(stats["cohen_kappa"], 0.9230769230769231)


if __name__ == "__main__":
    unittest.main()
