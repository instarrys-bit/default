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
        self.assertIn("gh workflow run self-healing-tests.yml --ref \"$BRANCH\"", workflow)
        self.assertNotIn("gh pr merge", workflow)
        self.assertIn("No speculative code changes were made.", workflow)

    def test_stale_watchdog_threshold_exceeds_main_job_timeout(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        auto_sync = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 300", auto_sync)
        self.assertIn("> 21600", workflow)

    def test_manifest_reconciliation_runs_after_final_config_precedence(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertLess(
            workflow.index("Enforce final ss.conf precedence after all rule mutations"),
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

    def test_missing_or_completed_review_cursor_is_a_successful_noop(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertIn('print("Cursor is not in progress; no checkpoint needs persistence.")', workflow)
        self.assertIn('print("Cursor has no completed checkpoint; nothing to persist.")', workflow)

    def test_user_owned_config_is_never_added_to_repair_commit(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("git add .github/workflows/auto_sync.yml", workflow)
        self.assertNotIn("git add -A", workflow)
        self.assertNotIn("git add shadowrocket/ss.conf", workflow)


if __name__ == "__main__":
    unittest.main()
