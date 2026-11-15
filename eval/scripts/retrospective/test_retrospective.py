"""Synthetic-only tests for retrospective parsers and classification boundaries."""
from __future__ import annotations

import unittest

from run_r1 import classify, displayed_numeric_match
from run_r2 import detect
from run_r2_latex_sensitivity import detect_extended, parse_math_number
from run_r3 import SENTENCE, VARIANTS


class RetrospectiveTests(unittest.TestCase):
    def setUp(self):
        self.op = {"gene": "ENSG00000000001", "symbol": "TEST1", "log2FC": -2.0, "padj": .00012}

    def test_r1_policy_is_distinct_from_interface_omission(self):
        self.assertEqual(classify(True, False, False, False, policy=True), "INTENTIONALLY_WITHHELD_BY_POLICY")
        self.assertEqual(classify(True, False, False, False), "OMITTED_AT_INTERFACE")
        self.assertEqual(classify(True, True, False, False), "OMITTED_AT_RENDERER")
        self.assertEqual(classify(False, False, False, False), "UNAVAILABLE_UPSTREAM")

    def test_r1_numeric_row_requires_correct_values(self):
        self.assertTrue(displayed_numeric_match("| ENSG00000000001 | -2.000 | 1.2e-4 |", -2, .00012))
        self.assertFalse(displayed_numeric_match("| ENSG00000000001 | +2.000 | 1.2e-4 |", -2, .00012))

    def test_v1_content_requires_gene_and_labeled_values(self):
        text="TEST1: log2FC -2.0; adjusted p 1.2e-4"
        self.assertTrue(detect(self.op,text)["exact_numeric_content"])
        self.assertFalse(detect(self.op,"Another gene: log2FC -2.0; adjusted p 1.2e-4")["exact_numeric_content"])
        self.assertFalse(detect(self.op,"TEST1 had 2 donors and 0.00012 units")["exact_numeric_content"])

    def test_latex_extension_preserves_signed_values(self):
        text="| TEST1 | -2.0 | $1.2 \\times 10^{-4}$ |"
        self.assertFalse(detect(self.op,text)["exact_numeric_content"])
        self.assertEqual(detect_extended(self.op,text)[:2],(True,True))
        self.assertEqual(parse_math_number("$1.2 \\times 10^{-4}$"),.00012)
        self.assertFalse(detect_extended(self.op,"| TEST1 | +2.0 | $1.2 \\times 10^{-4}$ |")[1])

    def test_r3_edits_are_minimal(self):
        original="prefix "+SENTENCE+" suffix"
        for replacement in VARIANTS.values():
            changed=original.replace(SENTENCE,replacement,1)
            self.assertTrue(changed.startswith("prefix "))
            self.assertTrue(changed.endswith(" suffix"))
            self.assertNotIn(SENTENCE,changed)


if __name__=="__main__":unittest.main()
