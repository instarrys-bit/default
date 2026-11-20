import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github/workflows/automation-watchdog.yml"
AUTO_SYNC = ROOT / ".github/workflows/auto_sync.yml"


class ProductionQueueRoutingTests(unittest.TestCase):
    def test_watchdog_runs_are_unique_and_queue_supervision_is_serialized(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-automation-watchdog-${{ github.run_id }}", workflow)
        self.assertIn("group: shadowrocket-watchdog-task-supervision-main", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("Queue writes use CAS", workflow)

    def test_queue_supervision_has_one_fail_closed_scheduler_path(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        job = workflow.split("  task-queue-supervision:", 1)[1]
        self.assertIn("needs: [health-check]", job)
        self.assertIn("github.ref == 'refs/heads/main'", job)
        self.assertIn("python3 scripts/task_scheduler.py", job)
        self.assertIn("--max-tasks 1 run-once", job)
        self.assertNotIn("recover-expired || true", job)

    def test_stale_audit_checks_use_the_same_queue_aware_base_guard(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertEqual(workflow.count("bash scripts/verify_publish_base.sh --check-only"), 2)
        self.assertLess(workflow.index("Stop stale audit before discovery"), workflow.index("Discover candidate source repositories"))
        self.assertLess(workflow.index("Stop stale audit before expensive deterministic review"), workflow.index("Audit each domain:"))
        self.assertIn("group: shadowrocket-main-writer", workflow)
        self.assertIn("cancel-in-progress: false", workflow)

    def test_production_dispatch_is_fingerprint_based_and_single_sourced(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        control = (ROOT / "automation/production_control.json").read_text(encoding="utf-8")
        self.assertIn("production_intent.py", workflow)
        self.assertIn("enqueue-auto-sync", workflow)
        self.assertIn('"automatic_watchdog_dispatch": true', control)
        self.assertIn('"source_discovery_mode": "monolithic_fallback"', control)
        self.assertFalse((ROOT / ".github/workflows/source-discovery.yml").exists())
        self.assertFalse((ROOT / ".github/workflows/assessment-completion-relay.yml").exists())

    def test_auto_sync_requires_matching_persisted_watchdog_task(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("AUTOMATION_TASK_ID", workflow)
        self.assertIn("RESOURCE_LEASE_PROOF", workflow)
        self.assertIn("requester_program_id", workflow)
        self.assertIn("workflow_automation_watchdog", workflow)


if __name__ == "__main__":
    unittest.main()
