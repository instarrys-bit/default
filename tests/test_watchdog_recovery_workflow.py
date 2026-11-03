import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"


class WatchdogRecoveryWorkflowTests(unittest.TestCase):
    def test_watchdog_observes_completed_main_audit_runs(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn('    - cron: "0 * * * *"', workflow)
        self.assertIn('      - "Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn('      - "Validate Shadowrocket config against user baseline"', workflow)
        self.assertIn("types: [completed]", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)
        self.assertIn('last_success_sha="$(jq -r', workflow)
        self.assertIn('repos/$REPO/compare/$last_success_sha...$current_sha', workflow)
        self.assertIn("Last successful audit is healthy; any intervening main changes are documentation-only", workflow)

    def test_only_infrastructure_failures_trigger_bounded_scheduled_or_push_recovery(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('SOURCE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}', workflow)
        self.assertIn('SOURCE_EVENT: ${{ github.event.workflow_run.event }}', workflow)
        self.assertIn('SOURCE_WORKFLOW_NAME: ${{ github.event.workflow_run.name }}', workflow)
        self.assertIn("validator failures are handled by self-healing diagnosis", workflow)
        self.assertIn("block_manifest=true", workflow)
        self.assertIn("needs.health-check.outputs.block_manifest != 'true'", workflow)
        self.assertIn('timed_out|startup_failure)', workflow)
        self.assertNotIn('failure|timed_out|startup_failure)', workflow)
        self.assertIn("scripts/watchdog_recovery_policy.py", workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "schedule" ]', workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "push" ]', workflow)
        self.assertIn("gh workflow run auto_sync.yml --ref main --repo \"$REPO\"", workflow)
        self.assertIn('select(.head_branch == "main" and .head_sha == $sha and .id > $source', workflow)

    def test_run_history_checks_follow_all_api_pages(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("gh api --paginate --slurp"), 3)
        self.assertNotIn("runs?per_page=20", workflow)
        self.assertNotIn("runs?per_page=30", workflow)

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


    def test_existing_heartbeat_and_stale_run_monitor_cover_distinct_health_signals(self):
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        healing = (ROOT / ".github" / "workflows" / "self-healing-agent.yml").read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("reports/automation/heartbeat.json", audit)
        self.assertIn("Write successful audit heartbeat", audit)
        self.assertIn("stale-run-watch:", watchdog)
        self.assertNotIn("stale-run-watch:", healing)
        self.assertIn("run_started_at", watchdog)
        self.assertIn("21600", watchdog)
        self.assertIn("run.get(\"head_branch\") != \"main\"", watchdog)
        self.assertIn("gh run cancel", watchdog)

    def test_top_level_watchdog_supervises_remote_queue_fail_closed(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("task-queue-supervision:", workflow)
        self.assertIn("group: shadowrocket-task-queue", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("python3 scripts/task_scheduler.py", workflow)
        self.assertIn("--max-tasks 1 run-once", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)

    def test_watchdog_deduplicates_all_active_run_states_before_dispatch(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        for status in ("queued", "pending", "waiting", "requested", "in_progress"):
            self.assertIn(f'.status == "{status}"', workflow)
        self.assertIn("A deterministic audit for current main", workflow)

if __name__ == "__main__":
    unittest.main()
