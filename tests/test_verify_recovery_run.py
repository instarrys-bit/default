import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_recovery_run import AUDIT_WORKFLOW, PUBLISH_VERIFY_STEP, verify_recovery_run


def successful_run():
    return {
        "id": 123,
        "name": AUDIT_WORKFLOW,
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": "a" * 40,
    }


def successful_jobs():
    return {
        "jobs": [
            {"name": "audit", "conclusion": "success", "steps": []},
            {
                "name": "publish",
                "conclusion": "success",
                "steps": [{"name": PUBLISH_VERIFY_STEP, "conclusion": "success"}],
            },
        ]
    }


class VerifyRecoveryRunTests(unittest.TestCase):
    def test_requires_successful_audit_publish_and_remote_verification(self):
        result = verify_recovery_run(successful_run(), successful_jobs())
        self.assertTrue(result["verified"])
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["run_id"], "123")

    def test_rejects_overall_success_when_publish_verification_is_missing(self):
        jobs = successful_jobs()
        jobs["jobs"][1]["steps"] = []
        result = verify_recovery_run(successful_run(), jobs)
        self.assertFalse(result["verified"])
        self.assertIn("remote_publish_verification_missing_or_failed", result["reasons"])

    def test_rejects_publish_job_failure(self):
        jobs = successful_jobs()
        jobs["jobs"][1]["conclusion"] = "failure"
        result = verify_recovery_run(successful_run(), jobs)
        self.assertFalse(result["verified"])
        self.assertIn("publish_job_not_successful", result["reasons"])

    def test_rejects_audit_job_failure(self):
        jobs = successful_jobs()
        jobs["jobs"][0]["conclusion"] = "failure"
        result = verify_recovery_run(successful_run(), jobs)
        self.assertFalse(result["verified"])
        self.assertIn("audit_job_not_successful", result["reasons"])

    def test_rejects_wrong_branch_or_workflow(self):
        run = successful_run()
        run["head_branch"] = "feature"
        run["name"] = "Unrelated workflow"
        result = verify_recovery_run(run, successful_jobs())
        self.assertFalse(result["verified"])
        self.assertIn("run_not_main_branch", result["reasons"])
        self.assertIn("unexpected_workflow", result["reasons"])

    def test_rejects_incomplete_or_failed_run(self):
        run = successful_run()
        run["status"] = "in_progress"
        run["conclusion"] = "failure"
        result = verify_recovery_run(run, successful_jobs())
        self.assertFalse(result["verified"])
        self.assertIn("run_not_completed", result["reasons"])
        self.assertIn("run_not_successful", result["reasons"])


    def test_accepts_paginated_jobs_payload(self):
        jobs = successful_jobs()
        pages = [{"total_count": 1, "jobs": jobs["jobs"][:1]}, {"total_count": 1, "jobs": jobs["jobs"][1:]}]
        result = verify_recovery_run(successful_run(), pages)
        self.assertTrue(result["verified"])

    def test_rejects_invalid_jobs_payload(self):
        result = verify_recovery_run(successful_run(), {})
        self.assertFalse(result["verified"])
        self.assertIn("jobs_payload_invalid", result["reasons"])


if __name__ == "__main__":
    unittest.main()
