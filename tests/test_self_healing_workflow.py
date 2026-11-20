import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
STORAGE = ROOT / ".github" / "workflows" / "storage-management.yml"


class WatchdogRecoveryWorkflowTests(unittest.TestCase):
    def test_read_only_watchdog_health_check_does_not_block_the_main_writer(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        audit = AUTO_SYNC.read_text(encoding="utf-8")
        health = watchdog.split("  health-check:", 1)[1].split("  assessment-canary:", 1)[0]
        self.assertIn("group: shadowrocket-main-writer", audit)
        self.assertIn("contents: read", health)
        self.assertNotIn("contents: write", health)
        self.assertNotIn("group: shadowrocket-main-writer", health)
        self.assertIn("cancel-in-progress: false", audit)
        self.assertFalse((ROOT / ".github" / "workflows" / "request-intake.yml").exists())

    def test_watchdog_recovery_is_diagnostic_and_never_writes_repository_code(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        stale = watchdog.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        self.assertIn("actions: write", stale)
        self.assertIn("contents: read", stale)
        self.assertNotIn("contents: write", stale)
        self.assertNotIn("pull-requests: write", stale)
        self.assertNotIn("git add", stale)
        self.assertNotIn("git commit", stale)
        self.assertNotIn("git push", stale)
        self.assertNotIn("modules/uu.conf", stale)
        self.assertIn('gh run cancel "$stale_id"', stale)

    def test_watchdog_has_no_repository_write_or_pull_request_token(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        stale = watchdog.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        self.assertNotIn("GH_TOKEN: ${{ secrets.AUTOMATION_WRITE_TOKEN || github.token }}", stale)
        self.assertNotIn("contents: write", stale)
        self.assertNotIn("pull-requests: write", stale)
        self.assertIn("persist-credentials: false", watchdog)
        self.assertNotIn("gh pr create", watchdog)

    def test_failed_run_cursor_is_retained_without_repository_writes(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        cursor_job = workflow.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        self.assertIn("actions: write", cursor_job)
        self.assertIn("actions/upload-artifact", cursor_job)
        self.assertIn("failed-review-cursor-recovery", cursor_job)
        self.assertNotIn("contents: write", cursor_job)
        self.assertNotIn("git add", cursor_job)
        self.assertNotIn("git push", cursor_job)

    def test_failed_cursor_checkpoint_is_artifact_backed_not_committed(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        cursor_job = workflow.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        self.assertIn("actions/download-artifact", cursor_job)
        self.assertIn("actions/upload-artifact", cursor_job)
        self.assertNotIn("python3 scripts/persist_review_cursor.py", workflow)
        self.assertNotIn("git add -- sources/review_cursor.json", workflow)
        self.assertNotIn("git push origin HEAD:main", cursor_job)

    def test_protected_user_config_is_never_staged_or_published(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('git diff --quiet "$GITHUB_SHA" -- modules/uu.conf', workflow)
        self.assertIn('git diff --cached --quiet "$GITHUB_SHA" -- modules/uu.conf', workflow)
        self.assertIn("Protected config modules/uu.conf is staged; refusing to commit.", workflow)
        self.assertIn('"path": "modules/uu.conf"', workflow)
        self.assertIn("expected_config_blob_sha", watchdog)
        self.assertIn("modules/uu.conf", watchdog)

    def test_pipeline_failures_are_recorded_and_recovery_is_dispatched_to_storage_management(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        notify = workflow.split("  notify-failure:", 1)[1].split("  resolve-failure:", 1)[0]
        resolve = workflow.split("  resolve-failure:", 1)[1].split("  watchdog-reconciliation:", 1)[0]
        self.assertIn("Dispatch incident record to Storage Management", notify)
        self.assertIn("classification=PIPELINE_FAILURE", notify)
        self.assertIn("gh workflow run storage-management.yml", notify)
        self.assertIn("Dispatch verified incident recovery to Storage Management", resolve)
        self.assertIn("classifications=PIPELINE_FAILURE", resolve)
        self.assertIn("gh workflow run storage-management.yml", resolve)
        self.assertNotIn("gh issue", workflow)

    def test_failed_checkpoint_recovery_uses_paged_history_and_exact_run_artifacts(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        recovery = workflow.split("      - name: Restore latest failed-run review checkpoint and delta journal", 1)[1].split(
            "      - name: \"Audit each domain:", 1
        )[0]
        self.assertIn("GH_TOKEN:", recovery)
        self.assertIn("REPO: ${{ github.repository }}", recovery)
        self.assertIn("CURRENT_RUN_ID: ${{ github.run_id }}", recovery)
        self.assertIn("gh api --paginate --slurp", recovery)
        self.assertIn("failed-review-cursor-recovery", recovery)
        self.assertIn("gh run download \"$run_id\"", recovery)
        self.assertIn("cursor_status", recovery)

    def test_baseline_registration_uses_owner_history_and_repository_context(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        registrar = (ROOT / "scripts" / "register_config_baseline.py").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/register_config_baseline.py", workflow)
        self.assertIn("GITHUB_REPOSITORY: ${{ github.repository }}", workflow)
        self.assertIn("owner_approved_config_history", registrar)
        self.assertIn("baseline_source_sha", workflow)

    def test_superseded_failures_are_suppressed_while_a_newer_audit_is_active(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        stale = watchdog.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        self.assertIn('select(.head_branch == "main" and .head_sha == $sha', stale)
        self.assertIn("active_count", stale)
        self.assertIn("An audit is still queued, cancelling, or running", stale)
        self.assertIn('echo "queue_blocked=true" >> "$GITHUB_OUTPUT"', stale)

    def test_stale_watch_prioritizes_runtime_timeout_and_confirms_cancellation(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        stale = watchdog.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        self.assertIn('if $started != null and (now - $started) > 21600 then', stale)
        self.assertIn('elif .head_sha != $sha then', stale)
        self.assertIn('[.id, "superseded", (.head_sha // "")]', stale)
        self.assertIn("fromdateiso8601", stale)
        self.assertIn('gh run cancel "$stale_id"', stale)
        self.assertIn("Cancellation of audit", stale)
        self.assertIn("queue_blocked=true", stale)

    def test_watchdog_reconciles_durable_queue_every_fifteen_minutes(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/15 * * * *"', watchdog)
        self.assertIn('    - cron: "30 22 * * *"', watchdog)
        self.assertIn("Export durable repository JSON queue snapshot", watchdog)
        self.assertIn("automation/task_queue.json", watchdog)
        self.assertNotIn("  push:", AUTO_SYNC.read_text(encoding="utf-8"))

    def test_missing_failed_cursor_artifact_is_skipped_without_repository_write(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        recovery = workflow.split("      - name: Restore latest failed-run review checkpoint and delta journal", 1)[1].split(
            "      - name: \"Audit each domain:", 1
        )[0]
        self.assertIn('[ -n "$artifact_id" ] || continue', recovery)
        self.assertIn('[ -n "$cursor_file" ] || continue', recovery)
        self.assertIn("Ignoring incomplete failed-run checkpoint", recovery)
        self.assertNotIn("git push", recovery)
        self.assertNotIn("git add", recovery)

    def test_run_history_checks_follow_all_api_pages(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("gh api --paginate --slurp"), 1)
        self.assertGreaterEqual(watchdog.count("gh api --paginate --slurp"), 2)
        self.assertNotIn("runs?per_page=20", watchdog)
        self.assertNotIn("runs?per_page=30", watchdog)

    def test_permissions_are_scoped_to_the_jobs_that_need_them(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        storage = STORAGE.read_text(encoding="utf-8")
        cursor = workflow.split("  persist-review-cursor:", 1)[1].split("  notify-failure:", 1)[0]
        health = watchdog.split("  health-check:", 1)[1].split("  assessment-canary:", 1)[0]
        queue = watchdog.split("  task-queue-supervision:", 1)[1].split("  stale-run-watch:", 1)[0]
        stale = watchdog.split("  stale-run-watch:", 1)[1].split("  manifest-integrity:", 1)[0]
        self.assertIn("actions: write", cursor)
        self.assertNotIn("contents: write", cursor)
        self.assertIn("contents: read", health)
        self.assertNotIn("contents: write", health)
        self.assertIn("actions: write", queue)
        self.assertIn("contents: write", queue)
        self.assertIn("actions: write", stale)
        self.assertIn("contents: read", stale)
        self.assertNotIn("pull-requests: write", stale)
        for job_name in ("mutate-ledger", "poll-recent-actions-artifacts", "ingest-actions-artifacts"):
            self.assertIn(f"  {job_name}:", storage)
        self.assertNotIn("issues: write", storage)

    def test_incidents_close_only_after_independent_publish_verification(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertLess(
            workflow.index("Independently verify committed remote rulesets"),
            workflow.index("Dispatch verified incident recovery to Storage Management"),
        )
        self.assertIn('event_id="auto-sync-recovery-$RUN_ID"', workflow)
        self.assertIn("verification_url", workflow)
        self.assertIn("source_sha", workflow)
        self.assertIn("storage/v2/incidents.json", (ROOT / "storage" / "v2" / "incident_store.py").read_text(encoding="utf-8"))

    def test_watchdog_uses_bounded_infrastructure_retries_only(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        policy = (ROOT / "scripts" / "watchdog_recovery_policy.py").read_text(encoding="utf-8")
        self.assertIn("scripts/watchdog_recovery_policy.py", watchdog)
        self.assertIn('RETRYABLE_CONCLUSIONS = {"timed_out", "startup_failure", "cancelled"}', policy)
        self.assertIn("max_retries: int = 2", policy)
        self.assertIn("base_cooldown: timedelta = timedelta(minutes=15)", policy)
        self.assertNotIn("failure|timed_out|startup_failure|cancelled)", watchdog)
        self.assertIn("Timeout recovery suppressed by bounded recovery policy", watchdog)

    def test_incident_state_machine_is_persisted_and_fail_closed(self):
        workflow = STORAGE.read_text(encoding="utf-8")
        state_machine = (ROOT / "scripts" / "incident_state.py").read_text(encoding="utf-8")
        self.assertIn("storage/v2/incidents.json", workflow)
        self.assertIn("incident_store.py", workflow)
        self.assertIn("incident-state:v1", state_machine)
        self.assertNotIn("gh issue", workflow)

    def test_incident_deduplication_is_scoped_to_source_revision(self):
        store = (ROOT / "storage" / "v2" / "incident_store.py").read_text(encoding="utf-8")
        self.assertIn("incident_key(workflow, source_sha, classification)", store)
        self.assertIn("storage/v2/incidents.json", store)
        self.assertIn('event_id="auto-sync-failure-$RUN_ID"', AUTO_SYNC.read_text(encoding="utf-8"))

    def test_retired_self_healing_entry_point_is_not_reintroduced(self):
        workflows = {path.name for path in (ROOT / ".github" / "workflows").glob("*.yml")}
        self.assertEqual(
            workflows,
            {"auto_sync.yml", "automation-watchdog.yml", "dashboard-pages.yml", "storage-management.yml"},
        )
        self.assertNotIn("self-healing-agent.yml", workflows)


if __name__ == "__main__":
    unittest.main()
