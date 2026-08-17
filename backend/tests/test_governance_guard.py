"""Fail-closed tests for the evaluation-only governance toggle."""

import os
import unittest
from unittest.mock import patch

from backend.agent.governance import governance_enabled


class TestGovernanceGuard(unittest.TestCase):
    def test_off_flag_alone_does_not_disable_governance(self):
        with patch.dict(os.environ, {"AGENT_GOVERNANCE": "off"}, clear=True):
            self.assertTrue(governance_enabled())

    def test_null_harness_context_allows_ablation(self):
        with patch.dict(os.environ, {
            "AGENT_GOVERNANCE": "off",
            "AGENT_EVALUATION_CONTEXT": "null_harness",
        }, clear=True):
            self.assertFalse(governance_enabled())

    def test_context_without_off_flag_remains_governed(self):
        with patch.dict(os.environ, {
            "AGENT_GOVERNANCE": "on",
            "AGENT_EVALUATION_CONTEXT": "null_harness",
        }, clear=True):
            self.assertTrue(governance_enabled())


if __name__ == "__main__":
    unittest.main()
