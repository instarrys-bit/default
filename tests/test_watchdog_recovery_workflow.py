import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"


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

    def test_successful_workflow_reports_degraded_source_discovery_health(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Report degraded source discovery health", workflow)
        self.assertIn(".source_discovery.search_error_count", workflow)
        self.assertIn(".coverage.stalled", workflow)
        self.assertIn("Shadowrocket source discovery degraded health", workflow)
        self.assertIn("gh issue create", workflow)
        self.assertIn("gh issue close", workflow)
        self.assertIn("issues: write", workflow)

    def test_successful_audit_writes_and_publishes_a_durable_heartbeat(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("Write successful audit heartbeat", workflow)
        self.assertIn('"status": "audit_passed"', workflow)
        self.assertIn('"modified_by_automation": False', workflow)
        self.assertIn("reports/automation/heartbeat.json", workflow)
        self.assertIn("git add --", workflow)


if __name__ == "__main__":
    unittest.main()
