import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_workflow_failure import diagnose


class DiagnoseWorkflowFailureTests(unittest.TestCase):
    def test_manifest_count_missing_selects_only_allowlisted_repair(self):
        result = diagnose(
            "##[group]Run python3 scripts/audit_ruleset_references.py\n"
            "direct.list line count 216 differs from manifest DIRECT count None\n"
            "##[error]Process completed with exit code 1.\n",
            "123",
        )
        self.assertEqual(result["classification"], "RULESET_MANIFEST_COUNT_MISSING")
        self.assertEqual(result["repair_id"], "refresh_ruleset_manifest")
        self.assertTrue(result["automatic_code_change_allowed"])

    def test_unknown_failure_never_authorizes_code_change(self):
        result = diagnose("RuntimeError: unknown internal failure\n##[error]Process completed with exit code 1.")
        self.assertEqual(result["classification"], "UNCLASSIFIED_STEP_FAILURE")
        self.assertIsNone(result["repair_id"])
        self.assertFalse(result["automatic_code_change_allowed"])

    def test_timeout_is_classified_without_code_repair(self):
        result = diagnose("Job exceeded maximum execution time")
        self.assertEqual(result["classification"], "WORKFLOW_TIMEOUT")
        self.assertFalse(result["automatic_code_change_allowed"])


if __name__ == "__main__":
    unittest.main()
