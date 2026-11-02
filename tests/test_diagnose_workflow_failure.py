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

    def test_stale_concurrency_test_contract_has_a_narrow_allowlisted_repair(self):
        result = diagnose(
            "##[group]Run python3 -m unittest tests.test_workflow_config_guard_order\n"
            "FAIL: test_stale_audit_guard_runs_before_expensive_domain_review\n"
            "AssertionError: 'cancel-in-progress: true' not found in workflow containing cancel-in-progress: false\n"
            "##[error]Process completed with exit code 1.\n"
        )
        self.assertEqual(result["classification"], "WORKFLOW_TEST_CONTRACT_MISMATCH")
        self.assertEqual(result["repair_id"], "fix_stale_audit_concurrency_contract")
        self.assertTrue(result["automatic_code_change_allowed"])

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

    def test_early_stale_guard_is_not_reported_as_a_failure_incident(self):
        result = diagnose(
            "##[group]Run set -euo pipefail\n"
            "Audit commit 3569cc1df8e7070f526d3048c22aaa1101e752a8 is stale; "
            "current main is 038cb4fb95075a9378b985a65d60aca55fd1029e. "
            "Stopping before source discovery.\n"
            "##[error]Process completed with exit code 1.\n",
            "41415056174",
        )
        self.assertEqual(result["classification"], "STALE_SUPERSEDED")
        self.assertIsNone(result["repair_id"])
        self.assertFalse(result["automatic_code_change_allowed"])


    def test_empty_or_unusable_log_is_not_reported_as_incident(self):
        result = diagnose("downloaded log was empty")
        self.assertEqual(result["classification"], "INSUFFICIENT_FAILURE_EVIDENCE")
        self.assertEqual(result["failed_steps"], [])
        self.assertEqual(result["evidence"], [])


    def test_config_baseline_mismatch_is_reported_without_authorizing_config_edits(self):
        result = diagnose(
            "ERROR: User config baseline mismatch for shadowrocket/ss.conf: "
            + "2e528134059b629605d20b52481516dd16a53580; expected "
            + "315b8fbd168b834df9dbc52b551b823221c5d99f\n"
            + "##[error]Process completed with exit code 1.",
            "456",
        )
        self.assertEqual(result["classification"], "CONFIG_BASELINE_MISMATCH")
        self.assertIsNone(result["repair_id"])
        self.assertFalse(result["automatic_code_change_allowed"])
        self.assertEqual(len(result["evidence"]), 1)


    def test_baseline_registration_failure_is_classified_as_config_baseline_mismatch(self):
        result = diagnose(
            "ERROR: ss.conf differs from the approved baseline, but this run is not an owner-authored push changing ss.conf; refusing automatic approval.\\n"
            "##[error]Process completed with exit code 1.",
            "789",
        )
        self.assertEqual(result["classification"], "CONFIG_BASELINE_MISMATCH")
        self.assertIsNone(result["repair_id"])
        self.assertFalse(result["automatic_code_change_allowed"])
        self.assertTrue(any("ss.conf" in item for item in result["evidence"]))


    def test_baseline_diagnostics_cover_both_verification_and_registration_errors(self):
        samples = [
            "ERROR: User config baseline mismatch for shadowrocket/ss.conf: "
            "2e528134059b629605d20b52481516dd16a53580; expected "
            "315b8fbd168b834df9dbc52b551b823221c5d99f",
            "ERROR: ss.conf differs from the approved baseline, but this run is not an owner-authored push changing ss.conf; refusing automatic approval.",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                result = diagnose(sample + "\\n##[error]Process completed with exit code 1.")
                self.assertEqual(result["classification"], "CONFIG_BASELINE_MISMATCH")
                self.assertIsNone(result["repair_id"])
                self.assertFalse(result["automatic_code_change_allowed"])


if __name__ == "__main__":
    unittest.main()
