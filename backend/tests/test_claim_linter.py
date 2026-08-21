"""Regression tests for claim-linter significance negation."""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval"))

from claim_linter import has_positive_significance_claim


class TestClaimLinter(unittest.TestCase):
    def test_subject_between_no_and_statistically_significant_is_negated(self):
        self.assertFalse(has_positive_significance_claim(
            "Conclusion: No genes are statistically significant."
        ))

    def test_none_are_significant_is_negated(self):
        self.assertFalse(has_positive_significance_claim(
            "None were statistically significant after correction."
        ))

    def test_positive_claim_remains_detected(self):
        self.assertTrue(has_positive_significance_claim(
            "Several genes are statistically significant."
        ))


if __name__ == "__main__":
    unittest.main()
