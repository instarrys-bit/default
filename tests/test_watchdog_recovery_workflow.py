import json
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
        self.assertIn('      - "Validate self-healing agent"', workflow)
        self.assertIn("types: [completed]", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)
        self.assertIn('last_success_sha="$(jq -r', workflow)
        self.assertIn('repos/$REPO/compare/$last_success_sha...$current_sha', workflow)
        self.assertIn("The latest successful audit is healthy; intervening main changes are documentation or strictly verified queue state.", workflow)
        self.assertIn("bash scripts/verify_publish_base.sh --check-only", workflow)

    def test_only_infrastructure_failures_trigger_bounded_scheduled_or_push_recovery(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('SOURCE_CONCLUSION: ${{ github.event.workflow_run.conclusion }}', workflow)
        self.assertIn('SOURCE_EVENT: ${{ github.event.workflow_run.event }}', workflow)
        self.assertIn('SOURCE_WORKFLOW_NAME: ${{ github.event.workflow_run.name }}', workflow)
        self.assertIn("and self-healing failures have their own diagnosis paths.", workflow)
        self.assertIn("block_manifest=true", workflow)
        self.assertIn("needs.health-check.outputs.block_manifest != 'true'", workflow)
        self.assertIn('timed_out|startup_failure)', workflow)
        self.assertNotIn('failure|timed_out|startup_failure)', workflow)
        self.assertIn("scripts/watchdog_recovery_policy.py", workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "schedule" ]', workflow)
        self.assertIn('[ "$SOURCE_EVENT" != "push" ]', workflow)
        self.assertIn("enqueue-auto-sync", workflow)
        self.assertNotIn("gh workflow run auto_sync.yml", workflow)
        self.assertIn('select(.head_branch == "main" and .head_sha == $sha and .id > $source', workflow)

    def test_run_history_checks_follow_all_api_pages(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("gh api --paginate --slurp"), 3)
        self.assertNotIn("runs?per_page=20", workflow)
        self.assertNotIn("runs?per_page=30", workflow)

    def test_workflow_dispatch_recovery_does_not_recursively_retry(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Workflow-dispatch run has no durable queue task correlation; refusing automatic recovery.", workflow)
        self.assertIn("github.event_name == 'workflow_run'", workflow)
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("A valid Watchdog task correlation is required", audit)
        self.assertIn('task.get("requester_program_id") != "workflow_automation_watchdog"', audit)
        self.assertIn('task.get("status") not in {"CLAIMED", "VERIFYING"}', audit)

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
        self.assertIn("needs.stale-run-watch.result == 'success'", workflow)
        self.assertIn("needs: [health-check, stale-run-watch, manifest-integrity]", workflow)
        job_start = workflow.index("  task-queue-supervision:")
        job_end = workflow.index("  stale-run-watch:", job_start)
        queue_job = workflow[job_start:job_end]
        self.assertIn("      actions: write", queue_job)
        self.assertIn("      contents: write", queue_job)
        self.assertNotIn("      issues: write", queue_job)
        self.assertIn("persist-credentials: false", queue_job)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn('queue_token="$GITHUB_TOKEN"', workflow)
        self.assertIn("unset GITHUB_TOKEN", workflow)
        self.assertIn("--token-stdin", workflow)
        self.assertIn("python3 scripts/task_scheduler.py", workflow)
        self.assertIn("--max-tasks 1 run-once", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)

    def test_production_audit_is_watchdog_queue_owned(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("enqueue_auto_sync_task", (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8"))
        self.assertIn("enqueue-auto-sync", workflow)
        self.assertNotIn("gh workflow run auto_sync.yml", workflow)
        self.assertNotIn("  schedule:", audit.split("  workflow_dispatch:", 1)[0])
        self.assertNotIn("  push:", audit.split("  permissions:", 1)[0])
        self.assertIn("  workflow_dispatch:", audit)

    def test_watchdog_deduplicates_all_active_run_states_before_dispatch(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        for status in ("queued", "pending", "waiting", "requested", "in_progress"):
            self.assertIn(f'.status == "{status}"', workflow)
        self.assertIn("A deterministic audit for current main", workflow)

    def test_queue_and_activation_contract_changes_wake_the_watchdog(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        for path in (
            "automation/program_registry.json",
            "automation/execution_adapters.json",
        ):
            self.assertIn(f'      - "{path}"', workflow)
        self.assertNotIn('"automation/task_queue.json"', workflow.split("permissions:", 1)[0])
        self.assertNotIn('"rulesets/**"', workflow.split("permissions:", 1)[0])
        self.assertNotIn('"sources/**"', workflow.split("permissions:", 1)[0])
    def test_completion_dispatch_cannot_create_production_demand(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        step = workflow.split("      - name: Detect stale successful audit and recover", 1)[1].split("  task-queue-supervision:", 1)[0]
        self.assertIn("github.event_name == 'push'", step)
        self.assertIn("github.event_name == 'schedule'", step)
        self.assertIn("github.event_name == 'workflow_dispatch'", step)
        self.assertNotIn("github.event_name == 'repository_dispatch'", step)
        self.assertIn("repository_dispatch:", workflow)
        self.assertIn("automation-production-completed", workflow)


if __name__ == "__main__":
    unittest.main()
