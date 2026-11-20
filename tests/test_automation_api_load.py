import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
DASHBOARD = WORKFLOWS / "dashboard-pages.yml"
WATCHDOG = WORKFLOWS / "automation-watchdog.yml"


class AutomationApiLoadTests(unittest.TestCase):
    def test_dashboard_refresh_is_bounded_to_current_producers(self):
        workflow = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/30 * * * *"', workflow)
        self.assertIn('"Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn('"Shadowrocket automation watchdog"', workflow)
        self.assertIn('"Storage Management"', workflow)
        self.assertNotIn("Source Discovery (Watchdog)", workflow)
        self.assertNotIn("self-healing agent", workflow)

    def test_only_the_four_retained_workflows_are_present(self):
        self.assertEqual(sorted(p.name for p in WORKFLOWS.glob("*.yml")), [
            "auto_sync.yml", "automation-watchdog.yml", "dashboard-pages.yml", "storage-management.yml"
        ])

    def test_watchdog_has_one_periodic_supervision_entrypoint(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/15 * * * *"', workflow)
        self.assertIn("task-queue-supervision:", workflow)
        self.assertIn("run-once", workflow)
        self.assertFalse((WORKFLOWS / "queue-snapshot-artifact.yml").exists())


if __name__ == "__main__":
    unittest.main()
