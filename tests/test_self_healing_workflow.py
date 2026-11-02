import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "self-healing-agent.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"


class SelfHealingWorkflowTests(unittest.TestCase):
    def test_repair_is_bounded_and_does_not_auto_merge(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("fix_stale_audit_concurrency_contract", workflow)
        self.assertIn("git add -- .github/workflows/auto_sync.yml", workflow)
        self.assertIn("git add -- tests/test_workflow_config_guard_order.py", workflow)
        self.assertIn("fix_stale_audit_concurrency_contract", (ROOT / "scripts" / "apply_safe_repair.py").read_text(encoding="utf-8"))
        self.assertIn("refresh_ruleset_manifest)", workflow)
        self.assertIn("Unknown repair id at PR publication", workflow)
        self.assertIn("gh pr create", workflow)
        self.assertIn("id: publish-repair", workflow)
        self.assertIn("always() && steps.supersession.outputs.stale != 'true'", workflow)
        self.assertIn("steps.publish-repair.outcome == 'failure'", workflow)
        self.assertIn("steps.diagnosis.outputs.classification == 'WORKFLOW_TIMEOUT'", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'startup_failure'", workflow)
        self.assertIn("gh workflow run self-healing-tests.yml --ref \"$BRANCH\"", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertIn("No speculative code changes were made.", workflow)

    def test_self_healing_agent_failures_are_reported_and_recovered_per_workflow(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  report-agent-failure:", workflow)
        self.assertIn("needs.diagnose-and-repair.result == 'failure'", workflow)
        self.assertIn("shadowrocket-automation:agent_failure;workflow=deterministic_audit", workflow)
        self.assertIn("shadowrocket-automation:agent_failure;workflow=config_validator", workflow)
        self.assertIn("The deterministic audit and publish have recovered", workflow)
        self.assertIn("The config-baseline validator has recovered", workflow)

    def test_stale_watchdog_threshold_exceeds_main_job_timeout(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        auto_sync = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 300", auto_sync)
        self.assertIn("> 21600", workflow)

    def test_manifest_reconciliation_runs_after_final_config_scope_coverage(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertLess(
            workflow.index("Reconcile final ss.conf scope coverage after all rule mutations"),
            workflow.index("Reconcile final RULE-SET manifest counts"),
        )
        self.assertLess(
            workflow.index("Reconcile final RULE-SET manifest counts"),
            workflow.index("Build append-only rule-level provenance ledger"),
        )

    def test_write_token_is_not_exposed_to_repair_tests(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        repair_step = workflow.split("      - name: Apply allowlisted repair and run tests", 1)[1].split(
            "      - name: Publish repair pull request", 1
        )[0]
        self.assertNotIn("GH_TOKEN", repair_step)
        self.assertIn("persist-credentials: false", workflow)

    def test_owner_baseline_is_persisted_after_failed_audit(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        cursor_job = workflow.split("  persist-review-cursor:", 1)[1]
        self.assertIn("Persist owner-approved config baseline even when audit fails", cursor_job)
        self.assertIn("python3 scripts/register_config_baseline.py", cursor_job)
        self.assertIn("git add -- sources/policy.json sources/review_cursor.json", cursor_job)

    def test_missing_or_completed_review_cursor_is_a_successful_noop(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn('print("Cursor is not in progress; no checkpoint needs persistence.")', workflow)
        self.assertIn('print("Cursor has no completed checkpoint; nothing to persist.")', workflow)

    def test_user_owned_config_is_never_added_to_repair_commit(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("expected_staged_path=\".github/workflows/auto_sync.yml\"", workflow)
        self.assertIn("expected_staged_path=\"tests/test_workflow_config_guard_order.py\"", workflow)
        self.assertIn('staged_paths="$(git diff --cached --name-only)"', workflow)
        self.assertNotIn("git add -A", workflow)
        self.assertNotIn("git add shadowrocket/ss.conf", workflow)


    def test_config_validator_failures_are_monitored_and_incidents_are_resolved_on_recovery(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('      - "Validate Shadowrocket config against user baseline"', workflow)
        self.assertIn("resolve-validator-incidents:", workflow)
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
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('run.get("head_sha") != current_main', workflow)
        self.assertIn('repos/$REPO/compare/$run_sha...$current_main', workflow)
        self.assertIn('only docs/ changed after its audited commit', workflow)
        self.assertIn('gh run cancel "$stale_id"', workflow)
        self.assertIn('gh workflow run auto_sync.yml --ref main', workflow)
        self.assertIn('An audit is still queued, cancelling, or running', workflow)



    def test_hourly_watchdog_is_the_recovery_entrypoint_without_self_triggering_pushes(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('    - cron: "0 * * * *"', workflow)
        self.assertNotIn("  push:", workflow)



    def test_run_history_checks_follow_all_api_pages(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("gh api --paginate --slurp"), 3)
        self.assertNotIn("runs?per_page=20", workflow)
        self.assertNotIn("runs?per_page=30", workflow)

    def test_permissions_are_scoped_to_the_jobs_that_need_them(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        top_level = workflow.split("jobs:", 1)[0]
        self.assertIn("permissions:" + chr(10) + "  contents: read", top_level)
        self.assertNotIn("contents: write", top_level)
        diagnose = workflow.split("  diagnose-and-repair:", 1)[1].split("  resolve-validator-incidents:", 1)[0]
        self.assertIn("contents: write", diagnose)
        resolver = workflow.split("  resolve-validator-incidents:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn("issues: write", resolver)
        self.assertNotIn("contents: write", resolver)
        watcher = workflow.split("  stale-run-watch:", 1)[1]
        self.assertIn("actions: write", watcher)
        self.assertIn("contents: read", watcher)
        self.assertNotIn("pull-requests: write", watcher)



    def test_audit_incidents_close_only_after_independent_publish_verification(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        resolver = workflow.split("  resolve-audit-incidents:", 1)[1].split("  stale-run-watch:", 1)[0]
        self.assertIn('gh api "repos/$REPO/actions/runs/$RUN_ID"', resolver)
        self.assertIn('gh api --paginate --slurp "repos/$REPO/actions/runs/$RUN_ID/jobs?per_page=100"', resolver)
        self.assertIn("python3 scripts/verify_recovery_run.py", resolver)
        self.assertIn("actions: read", resolver)
        self.assertIn("contents: read", resolver)
        self.assertIn("Checkout verifier code", resolver)
        self.assertIn("--paginate --slurp", resolver)
        self.assertLess(
            resolver.index("python3 scripts/verify_recovery_run.py"),
            resolver.index('\\n          issues="$(gh issue list'),
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
        self.assertNotIn("gh run cancel", watchdog.split("  manifest-integrity:", 1)[0])
        self.assertIn("persist-credentials: false", watchdog)
        self.assertNotIn("shadowrocket/ss.conf", policy)
        stale_watcher = (ROOT / ".github" / "workflows" / "self-healing-agent.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/watchdog_recovery_policy.py --source-run-id 0 --source-sha", stale_watcher)
        self.assertIn("Scheduled recovery suppressed", stale_watcher)


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
