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
        result = diagnose(
            "##[group]Run python3 scripts/unrecognized.py\n"
            "RuntimeError: unknown internal failure\n"
            "##[error]Process completed with exit code 1."
        )
        self.assertEqual(result["classification"], "UNCLASSIFIED_STEP_FAILURE")
        self.assertIsNone(result["repair_id"])
        self.assertFalse(result["automatic_code_change_allowed"])

    def test_timeout_is_classified_without_code_repair(self):
        result = diagnose("Job exceeded maximum execution time")
        self.assertEqual(result["classification"], "WORKFLOW_TIMEOUT")
        self.assertFalse(result["automatic_code_change_allowed"])

    def test_superseded_audit_is_not_an_incident_or_repair(self):
        result = diagnose(
            "##[group]Run set -euo pipefail\n"
            "Audit commit 3569cc1df8e7070f526d3048c22aaa1101e752a8 is stale; "
            "current main is 038cb4fb95075a9378b985a65d60aca55fd1029e. "
            "Refusing to spend resources on stale review inputs.\n"
            "##[error]Process completed with exit code 1.\n",
            "41415056173",
        )
        self.assertEqual(result["classification"], "STALE_SUPERSEDED")
        self.assertFalse(result["automatic_code_change_allowed"])
        self.assertIsNone(result["repair_id"])
        self.assertEqual(len(result["evidence"]), 1)

    def test_empty_or_unusable_log_is_not_reported_as_incident(self):
        result = diagnose("downloaded log was empty")
        self.assertEqual(result["classification"], "INSUFFICIENT_FAILURE_EVIDENCE")
        self.assertEqual(result["failed_steps"], [])
        self.assertEqual(result["evidence"], [])


if __name__ == "__main__":
    unittest.main()
