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
