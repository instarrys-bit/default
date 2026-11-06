import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "self-healing-agent.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"
REQUEST_INTAKE = ROOT / ".github" / "workflows" / "request-intake.yml"
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"


class SelfHealingWorkflowTests(unittest.TestCase):
    def test_repository_mutating_workflows_share_the_main_writer_concurrency_group(self):
        healing = WORKFLOW.read_text(encoding="utf-8")
        intake = REQUEST_INTAKE.read_text(encoding="utf-8")
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        for workflow in (healing, audit):
            self.assertIn("group: shadowrocket-main-writer", workflow)
            self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("group: shadowrocket-domain-intake", intake)
        self.assertIn("contents: read", intake)
        self.assertIn("issues: write", intake)
        self.assertNotIn("git push", intake)
    def test_self_healing_is_diagnostic_only_and_never_writes_repository_code(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        diagnose = workflow.split("  diagnose-and-repair:", 1)[1].split("  report-agent-failure:", 1)[0]
        self.assertIn("Automatic repository code repair is disabled", diagnose)
        self.assertNotIn("contents: write", diagnose)
        self.assertNotIn("pull-requests: write", diagnose)
        self.assertNotIn("git add", diagnose)
        self.assertNotIn("git commit", diagnose)
        self.assertNotIn("git push", diagnose)
        self.assertNotIn("gh pr create", diagnose)
        self.assertIn("gh issue create", diagnose)

    def test_self_healing_has_no_repository_write_or_pr_token(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        diagnose = workflow.split("  diagnose-and-repair:", 1)[1].split("  report-agent-failure:", 1)[0]
        repair_step = diagnose.split("      - name: Keep self-healing read-only", 1)[1].split("      - name: Open incident when no safe repair applies", 1)[0]
        self.assertNotIn("GH_TOKEN", repair_step)
        self.assertNotIn("contents: write", repair_step)
        self.assertNotIn("pull-requests: write", repair_step)
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("gh pr create", workflow)

    def test_failed_run_cursor_is_retained_without_repository_writes(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        cursor_job = workflow.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        self.assertIn("actions: write", cursor_job)
        self.assertIn("actions/upload-artifact", cursor_job)
        self.assertIn("failed-review-cursor-recovery", cursor_job)
        self.assertNotIn("contents: write", cursor_job)
        self.assertNotIn("git add", cursor_job)
        self.assertNotIn("git push", cursor_job)
        self.assertNotIn("sources/review_cursor.json", cursor_job.split("Preserve cursor without writing repository files", 1)[-1].split("retention-days", 1)[-1])

    def test_failed_cursor_checkpoint_is_not_persisted_to_repository(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        cursor_job = workflow.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        self.assertIn("actions/download-artifact", cursor_job)
        self.assertIn("actions/upload-artifact", cursor_job)
        self.assertNotIn("python3 scripts/persist_review_cursor.py", workflow)
        self.assertNotIn("git add -- sources/review_cursor.json", workflow)
        self.assertNotIn("git push origin HEAD:main", cursor_job)

    def test_self_healing_cannot_write_repository_files(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        diagnose = workflow.split("  diagnose-and-repair:", 1)[1].split("  report-agent-failure:", 1)[0]
        self.assertNotIn("git add", diagnose)
        self.assertNotIn("git commit", diagnose)
        self.assertNotIn("git push", diagnose)
        self.assertNotIn("modules/uu.conf", diagnose)


    def test_config_validator_failures_are_monitored_and_incidents_are_resolved_on_recovery(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('      - "Validate Shadowrocket config against user baseline"', workflow)
        self.assertIn("resolve-validator-incidents:", workflow)
        resolver = workflow.split("  resolve-validator-incidents:", 1)[1].split("  resolve-audit-incidents:", 1)[0]
        self.assertIn("contents: read", resolver)
        self.assertIn("Checkout incident state helper", resolver)
        self.assertNotIn("\\\\n", resolver)
        self.assertIn("validator-verifying-$RUN_ID-$issue", resolver)
        self.assertIn("validator-success-$RUN_ID-$issue", resolver)
        self.assertIn("persist-credentials: false", resolver)
        self.assertIn("CONFIG_BASELINE_MISMATCH TEST_FAILURE PYTHON_IMPORT_FAILURE", workflow)
        self.assertIn("The protected config was not modified.", workflow)

    def test_baseline_registration_has_owner_history_credentials(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("GH_TOKEN: ${{ github.token }}"), 2)
        self.assertGreaterEqual(workflow.count("GITHUB_REPOSITORY: ${{ github.repository }}"), 2)
        self.assertIn("owner_approved_config_history", (ROOT / "scripts" / "register_config_baseline.py").read_text(encoding="utf-8"))



    def test_superseded_failures_are_suppressed_when_a_newer_run_is_active_or_successful(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Check whether a newer run supersedes this failure", workflow)
        self.assertIn("FAILED_SHA: ${{ github.event.workflow_run.head_sha }}", workflow)
        self.assertIn("repos/$REPO/compare/$FAILED_SHA...$current_main", workflow)
        self.assertIn('select(.head_branch == "main" and .id > $failed)', workflow)
        self.assertIn('select(.status != "completed" or .conclusion == "success")', workflow)
        self.assertIn("steps.supersession.outputs.stale != 'true'", workflow)



    def test_stale_watch_cancels_superseded_audits_before_timeout(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('if .head_sha != $sha then [.id, "superseded"', workflow)
        self.assertIn("fromdateiso8601", workflow)
        self.assertIn('repos/$REPO/compare/$run_sha...$current_main', workflow)
        self.assertIn('only docs/ changed after its audited commit', workflow)
        self.assertIn('gh run cancel "$stale_id"', workflow)
        self.assertIn('enqueue-auto-sync', workflow)
        self.assertNotIn('gh workflow run auto_sync.yml', workflow)
        self.assertIn('An audit is still queued, cancelling, or running', workflow)



    def test_hourly_watchdog_is_the_recovery_entrypoint_without_self_triggering_pushes(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertNotIn('    - cron: "0 * * * *"', workflow)
        self.assertIn('    - cron: "0 * * * *"', watchdog)
        self.assertNotIn("  push:", workflow)
        self.assertNotIn("  stale-run-watch:", workflow)



    def test_run_history_checks_follow_all_api_pages(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("gh api --paginate --slurp"), 2)
        self.assertNotIn("runs?per_page=20", workflow)
        self.assertNotIn("runs?per_page=30", workflow)

    def test_permissions_are_scoped_to_the_jobs_that_need_them(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        top_level = workflow.split("jobs:", 1)[0]
        self.assertIn("permissions:" + chr(10) + "  contents: read", top_level)
        self.assertNotIn("contents: write", top_level)
        diagnose = workflow.split("  diagnose-and-repair:", 1)[1].split("  resolve-validator-incidents:", 1)[0]
        self.assertIn("contents: read", diagnose)
        self.assertNotIn("contents: write", diagnose)
        resolver = workflow.split("  resolve-validator-incidents:", 1)[1].split("  resolve-audit-incidents:", 1)[0]
        self.assertIn("issues: write", resolver)
        self.assertNotIn("contents: write", resolver)
        watcher = WATCHDOG.read_text(encoding="utf-8").split("  stale-run-watch:", 1)[1]
        self.assertIn("actions: write", watcher)
        self.assertIn("contents: read", watcher)
        self.assertNotIn("pull-requests: write", watcher)
        health_check = WATCHDOG.read_text(encoding="utf-8").split("  health-check:", 1)[1].split("  task-queue-supervision:", 1)[0]
        self.assertIn("contents: read", health_check)



    def test_audit_incidents_close_only_after_independent_publish_verification(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        resolver = workflow.split("  resolve-audit-incidents:", 1)[1]
        self.assertIn('gh api "repos/$REPO/actions/runs/$RUN_ID"', resolver)
        self.assertIn('gh api --paginate --slurp "repos/$REPO/actions/runs/$RUN_ID/jobs?per_page=100"', resolver)
        self.assertIn("python3 scripts/verify_recovery_run.py", resolver)
        self.assertIn("actions: read", resolver)
        self.assertIn("contents: read", resolver)
        self.assertIn("Checkout verifier code", resolver)
        self.assertIn("--paginate --slurp", resolver)
        self.assertLess(
            resolver.index("python3 scripts/verify_recovery_run.py"),
            resolver.index('          issues="$(gh issue list'),
        )
        self.assertIn("Independently verify committed remote rulesets", AUTO_SYNC.read_text(encoding="utf-8"))

    def test_watchdog_uses_bounded_infrastructure_retries_only(self):
        watchdog = (ROOT / ".github" / "workflows" / "automation-watchdog.yml").read_text(encoding="utf-8")
        policy = (ROOT / "scripts" / "watchdog_recovery_policy.py").read_text(encoding="utf-8")
        self.assertIn("SOURCE_SHA: ${{ github.event.workflow_run.head_sha }}", watchdog)
        self.assertIn("timed_out|startup_failure)", watchdog)
        self.assertNotIn("failure|timed_out|startup_failure)", watchdog)
        self.assertIn("scripts/watchdog_recovery_policy.py", watchdog)
        self.assertIn("RETRYABLE_CONCLUSIONS = {\"timed_out\", \"startup_failure\", \"cancelled\"}", policy)
        self.assertIn("max_retries: int = 2", policy)
        self.assertIn("base_cooldown: timedelta = timedelta(minutes=15)", policy)
        self.assertNotIn("gh run cancel", watchdog.split("  stale-run-watch:", 1)[0])
        self.assertIn("persist-credentials: false", watchdog)
        self.assertNotIn("modules/uu.conf", policy)
        stale_watcher = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("scripts/watchdog_recovery_policy.py --source-run-id 0 --source-sha", stale_watcher)
        self.assertIn("Timeout recovery suppressed by bounded recovery policy", stale_watcher)
        self.assertNotIn("Scheduled recovery suppressed", stale_watcher)


    def test_incident_state_machine_is_persisted_and_fail_closed(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        state_machine = ROOT / "scripts" / "incident_state.py"
        self.assertTrue(state_machine.exists())
        self.assertIn("--target-state MANUAL_INTERVENTION", workflow)
        self.assertIn("--target-state RECOVERED", workflow)
        self.assertIn("--verification-url", workflow)
        self.assertIn("gh issue edit \"$issue\" --repo \"$REPO\" --body-file /tmp/incident-state-body.md", workflow)
        self.assertIn("FAILED_SHA: ${{ github.event.workflow_run.head_sha }}", workflow)
        self.assertIn("incident-state:v1", state_machine.read_text(encoding="utf-8"))

    def test_incident_deduplication_is_scoped_to_source_revision(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('($workflow_key; ${FAILED_SHA:0:8})', workflow)
        self.assertIn("deterministic_audit(; [0-9a-f]{8})?", workflow)
        self.assertIn("config_validator(; [0-9a-f]{8})?", workflow)


if __name__ == "__main__":
    unittest.main()
