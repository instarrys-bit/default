import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "self-healing-agent.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"


class SelfHealingWorkflowTests(unittest.TestCase):
    def test_repair_is_bounded_and_does_not_auto_merge(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('[ "$REPAIR_ID" != "refresh_ruleset_manifest" ]', workflow)
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
        self.assertIn("git add .github/workflows/auto_sync.yml", workflow)
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



if __name__ == "__main__":
    unittest.main()
