import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"


class WatchdogStaleRunRecoveryTests(unittest.TestCase):
    def test_placeholder(self):
        self.assertTrue(WATCHDOG.is_file())
        content = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("task-queue-supervision:", content)
        self.assertIn("Persist production intent through the single queue writer", content)


class WatchdogV2ControlPlaneTests(unittest.TestCase):
    def test_simplified_watchdog_has_intent_and_supervision(self):
        text = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Detect production intent and enqueue durable auto-sync task", text)
        self.assertIn("Recover leases and run scheduler once", text)
        self.assertIn("group: shadowrocket-watchdog-control-plane-main", text)
        self.assertNotIn("stale-run-watch", text)
        self.assertNotIn("manifest-integrity:", text)

    def test_superseded_dead_letters_are_reconciled_before_scheduler_dispatch(self):
        text = WATCHDOG.read_text(encoding="utf-8")
        reconcile = "Reconcile superseded terminal production tasks"
        scheduler = "Recover leases and run scheduler once"
        self.assertIn(reconcile, text)
        self.assertIn('--current-main-sha "$GITHUB_SHA" resolve-superseded-dead-letters', text)
        self.assertLess(text.index(reconcile), text.index(scheduler))

    def test_stale_task_release_reawakens_production_intent_evaluation(self):
        text = WATCHDOG.read_text(encoding="utf-8")
        reconcile = "Reconcile superseded terminal production tasks"
        re_wake = "Re-wake Watchdog after stale production task release"
        scheduler = "Recover leases and run scheduler once"
        self.assertIn("id: superseded", text)
        self.assertIn("superseded_stale_production_task_ids", text)
        self.assertIn("needs.health-check.outputs.queue_task_json == ''", text)
        self.assertIn('gh api --method POST "repos/$REPO/actions/workflows/$WATCHDOG_WORKFLOW_ID/dispatches"', text)
        self.assertLess(text.index(reconcile), text.index(re_wake))
        self.assertLess(text.index(re_wake), text.index(scheduler))


class LargeCASCheckoutScopeTests(unittest.TestCase):
    def test_all_workflow_checkouts_exclude_content_addressed_payload_blobs(self):
        workflow_paths = (
            ".github/workflows/auto_sync.yml",
            ".github/workflows/automation-watchdog.yml",
            ".github/workflows/storage-management.yml",
            ".github/workflows/dashboard-pages.yml",
        )
        for relative_path in workflow_paths:
            with self.subTest(workflow=relative_path):
                content = (ROOT / relative_path).read_text(encoding="utf-8")
                checkout_count = content.count("uses: actions/checkout")
                self.assertGreater(checkout_count, 0)
                self.assertEqual(content.count("filter: blob:none"), checkout_count)
                self.assertEqual(content.count("sparse-checkout-cone-mode: false"), checkout_count)
                self.assertEqual(
                    content.count("!/storage/v2/artifacts/sha256/"),
                    checkout_count,
                )
