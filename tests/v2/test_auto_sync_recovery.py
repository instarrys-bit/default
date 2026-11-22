import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from verify_auto_sync_recovery import (
    AUTO_SYNC_WORKFLOW_ID,
    AUTO_SYNC_WORKFLOW_PATH,
    PUBLISH_VERIFY_STEP,
    verify_auto_sync_recovery,
)


RUN_ID = 44965841153
HEAD_SHA = "75843fd62149db810e776b429fb95b3c92350049"
REQUESTED_SHA = "934b94a091574616e28b14b220b010bcacd4f88b"


def successful_run():
    return {
        "id": RUN_ID,
        "workflow_id": AUTO_SYNC_WORKFLOW_ID,
        "path": AUTO_SYNC_WORKFLOW_PATH,
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "head_sha": HEAD_SHA,
        "html_url": f"https://github.com/instarrys-bit/default/actions/runs/{RUN_ID}",
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


def successful_queue():
    return {
        "revision": 140,
        "tasks": [
            {
                "task_id": "task_ddab0e5429ef471eb76405fd",
                "status": "SUCCEEDED",
                "dispatch_intent": {
                    "workflow_id": AUTO_SYNC_WORKFLOW_ID,
                    "workflow_path": AUTO_SYNC_WORKFLOW_PATH,
                    "requested_head_sha": REQUESTED_SHA,
                },
                "result": {
                    "workflow_id": AUTO_SYNC_WORKFLOW_ID,
                    "workflow_path": AUTO_SYNC_WORKFLOW_PATH,
                    "run_evidence": {
                        "run_id": RUN_ID,
                        "status": "completed",
                        "conclusion": "success",
                        "head_sha": HEAD_SHA,
                        "requested_head_sha": REQUESTED_SHA,
                        "head_sha_relationship": "queue_intent_commit_only",
                    },
                },
                "verification": {"status": "passed"},
            }
        ],
    }


class VerifyAutoSyncRecoveryTests(unittest.TestCase):
    def test_requires_exact_workflow_publish_verification_and_verified_queue_task(self):
        result = verify_auto_sync_recovery(successful_run(), successful_jobs(), successful_queue())
        self.assertTrue(result["verified"])
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["run_id"], str(RUN_ID))
        self.assertEqual(result["task_id"], "task_ddab0e5429ef471eb76405fd")

    def test_rejects_wrong_workflow_identity_or_branch(self):
        run = successful_run()
        run["workflow_id"] = AUTO_SYNC_WORKFLOW_ID + 1
        run["path"] = ".github/workflows/other.yml"
        run["head_branch"] = "feature"
        result = verify_auto_sync_recovery(run, successful_jobs(), successful_queue())
        self.assertFalse(result["verified"])
        self.assertIn("unexpected_workflow_id", result["reasons"])
        self.assertIn("unexpected_workflow_path", result["reasons"])
        self.assertIn("run_not_main_branch", result["reasons"])

    def test_rejects_overall_success_without_remote_publish_verification(self):
        jobs = successful_jobs()
        jobs["jobs"][1]["steps"] = []
        result = verify_auto_sync_recovery(successful_run(), jobs, successful_queue())
        self.assertFalse(result["verified"])
        self.assertIn("remote_publish_verification_missing_or_failed", result["reasons"])

    def test_rejects_failed_audit_or_publish_jobs(self):
        jobs = successful_jobs()
        jobs["jobs"][0]["conclusion"] = "failure"
        jobs["jobs"][1]["conclusion"] = "failure"
        result = verify_auto_sync_recovery(successful_run(), jobs, successful_queue())
        self.assertFalse(result["verified"])
        self.assertIn("audit_job_not_successful", result["reasons"])
        self.assertIn("publish_job_not_successful", result["reasons"])

    def test_rejects_missing_or_unverified_queue_task(self):
        queue = successful_queue()
        queue["tasks"][0]["verification"]["status"] = "failed"
        result = verify_auto_sync_recovery(successful_run(), successful_jobs(), queue)
        self.assertFalse(result["verified"])
        self.assertIn("independent_queue_verification_missing", result["reasons"])

    def test_rejects_queue_run_sha_or_requested_sha_mismatch(self):
        queue = successful_queue()
        queue["tasks"][0]["result"]["run_evidence"]["head_sha"] = "a" * 40
        result = verify_auto_sync_recovery(successful_run(), successful_jobs(), queue)
        self.assertFalse(result["verified"])
        self.assertIn("queue_run_evidence_mismatch", result["reasons"])

    def test_rejects_ambiguous_duplicate_queue_matches(self):
        queue = successful_queue()
        queue["tasks"].append(dict(queue["tasks"][0]))
        result = verify_auto_sync_recovery(successful_run(), successful_jobs(), queue)
        self.assertFalse(result["verified"])
        self.assertIn("matching_verified_queue_task_missing_or_ambiguous", result["reasons"])

    def test_storage_workflow_runs_retry_after_push_and_schedule_and_verifies_before_mutation(self):
        workflow = (ROOT / ".github" / "workflows" / "storage-management.yml").read_text(encoding="utf-8")
        self.assertIn("reconcile-verified-auto-sync-incidents:", workflow)
        self.assertIn("github.event_name == 'schedule' || github.event_name == 'push'", workflow)
        verify_at = workflow.index("verify_auto_sync_recovery.py")
        mutate_at = workflow.index("python3 storage/v2/incident_store.py resolve", verify_at)
        self.assertLess(verify_at, mutate_at)
        self.assertIn('event-id "auto-sync-recovery-$run_id"', workflow)


if __name__ == "__main__":
    unittest.main()
