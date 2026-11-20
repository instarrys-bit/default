import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / ".github" / "workflows" / "dashboard-pages.yml"
QUEUE_SNAPSHOT = ROOT / ".github" / "workflows" / "queue-snapshot-artifact.yml"


class AutomationApiLoadTests(unittest.TestCase):
    def test_dashboard_refresh_is_not_fanned_out_by_every_monitoring_workflow(self):
        workflow = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/30 * * * *"', workflow)
        self.assertIn('"Shadowrocket automation watchdog"', workflow)
        self.assertIn('"Shadowrocket Source Discovery (Watchdog)"', workflow)
        self.assertNotIn('"Validate Shadowrocket config against user baseline"', workflow)
        self.assertNotIn('"Shadowrocket self-healing agent"', workflow)
        self.assertNotIn('"Automation task manual"', workflow)

    def test_queue_snapshot_uses_its_periodic_schedule_without_duplicate_completion_fanout(self):
        workflow = QUEUE_SNAPSHOT.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/15 * * * *"', workflow)
        self.assertNotIn("  workflow_run:", workflow)


if __name__ == "__main__":
    unittest.main()
