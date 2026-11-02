import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"


class WatchdogRecoveryWorkflowTests(unittest.TestCase):
    def test_watchdog_observes_completed_main_audit_runs(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn('workflows: ["Shadowrocket Deterministic Domain Audit (User Config Baseline)"]', workflow)
        self.assertIn("types: [completed]", workflow)

    def test_failed_timed_out_or_startup_failed_scheduled_or_push_runs_trigger_one_recovery(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('SOURCE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}', workflow)
        self.assertIn('SOURCE_EVENT: ${{ github.event.workflow_run.event }}', workflow)
        self.assertIn('failure|timed_out|startup_failure)', workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "schedule" ]', workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "push" ]', workflow)
        self.assertIn("gh workflow run auto_sync.yml --ref main --repo \"$REPO\"", workflow)
        self.assertIn('select(.id > $source)', workflow)

    def test_workflow_dispatch_recovery_does_not_recursively_retry(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("A recovery run is workflow_dispatch; ignore its completion to prevent retry loops.", workflow)
        self.assertIn("github.event_name == 'workflow_run'", workflow)


if __name__ == "__main__":
    unittest.main()
