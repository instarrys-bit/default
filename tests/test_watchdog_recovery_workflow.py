import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"


@unittest.skip("V2 simplified watchdog: intent+supervision only; retired multi-job recovery plane")
class WatchdogStaleRunRecoveryTests(unittest.TestCase):
    def test_placeholder(self):
        self.assertTrue(WATCHDOG.is_file())


class WatchdogV2ControlPlaneTests(unittest.TestCase):
    def test_simplified_watchdog_has_intent_and_supervision(self):
        text = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("Detect production intent and enqueue durable auto-sync task", text)
        self.assertIn("Recover leases and run scheduler once", text)
        self.assertIn("group: shadowrocket-watchdog-control-plane-main", text)
        self.assertNotIn("stale-run-watch", text)
        self.assertNotIn("manifest-integrity:", text)
