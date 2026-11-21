import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / ".github" / "workflows" / "dashboard-pages.yml"
STORAGE = ROOT / ".github" / "workflows" / "storage-management.yml"
QUEUE_STORE = ROOT / "storage" / "v2" / "queue_store.py"


class AutomationApiLoadTests(unittest.TestCase):
    def test_dashboard_refresh_is_not_fanned_out_by_every_monitoring_workflow(self):
        workflow = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/30 * * * *"', workflow)
        self.assertIn('"Shadowrocket automation watchdog"', workflow)
        self.assertIn('"Storage Management"', workflow)
        self.assertIn('"Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertNotIn('"Shadowrocket Source Discovery (Watchdog)"', workflow)
        self.assertNotIn('"Validate Shadowrocket config against user baseline"', workflow)
        self.assertNotIn('"Shadowrocket self-healing agent"', workflow)

    def test_queue_snapshot_is_owned_by_scheduled_storage_management_not_a_second_workflow(self):
        workflow = STORAGE.read_text(encoding="utf-8")
        queue_store = QUEUE_STORE.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/15 * * * *"', workflow)
        self.assertIn("automation/task_queue.json", queue_store)
        self.assertIn("GitHubContentsJsonStore", queue_store)
        self.assertFalse((ROOT / ".github" / "workflows" / "queue-snapshot-artifact.yml").exists())
        self.assertFalse((ROOT / ".github" / "workflows" / "storage-incident-management.yml").exists())


if __name__ == "__main__":
    unittest.main()
