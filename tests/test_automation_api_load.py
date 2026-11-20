import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"
DASHBOARD = ROOT / ".github" / "workflows" / "dashboard-pages.yml"
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"


class AutomationApiLoadTests(unittest.TestCase):
    def test_config_validation_runs_in_the_protected_auto_sync_pipeline(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertNotIn("actions/artifacts/", workflow)
        self.assertNotIn("13731605096", workflow)
        self.assertIn("python3 -m unittest discover -s tests -v", workflow)
        self.assertIn("Verify registered user config baseline", workflow)
        self.assertIn("python3 scripts/verify_baseline.py --baseline-only", workflow)
        self.assertIn("Validate Shadowrocket config structure", workflow)
        self.assertIn("python3 scripts/validate_config.py", workflow)
        self.assertIn("python3 scripts/audit_config_drift.py", workflow)
        inputs = json.loads((ROOT / "automation" / "production_inputs.json").read_text(encoding="utf-8"))
        write_policy = json.loads((ROOT / "automation" / "resource_write_sets.json").read_text(encoding="utf-8"))["policy"]["protected_config"]
        self.assertIn("modules/uu.conf", inputs["production_input_paths"])
        self.assertEqual(write_policy["path"], "modules/uu.conf")
        self.assertEqual(write_policy["access"], "read_only")
        self.assertEqual(write_policy["writers_allowed"], [])
        self.assertEqual(write_policy["metadata_only_sync"]["allowed_paths"], [])
        self.assertIn("modules/uu.conf", write_policy["metadata_only_sync"]["never_write"])
        self.assertLess(
            workflow.index("Verify registered user config baseline"),
            workflow.index("Validate Shadowrocket config structure"),
        )
        self.assertLess(
            workflow.index("Validate Shadowrocket config structure"),
            workflow.index("Verify base commit and safely publish allowlisted outputs"),
        )

    def test_dashboard_refresh_is_not_fanned_out_by_retired_workflows(self):
        workflow = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/30 * * * *"', workflow)
        self.assertIn('"Shadowrocket Deterministic Domain Audit (User Config Baseline)"', workflow)
        self.assertIn('"Shadowrocket automation watchdog"', workflow)
        self.assertNotIn('"Shadowrocket Source Discovery (Watchdog)"', workflow)
        self.assertNotIn('"Validate Shadowrocket config against user baseline"', workflow)
        self.assertNotIn('"Shadowrocket self-healing agent"', workflow)
        self.assertNotIn('"Automation task manual"', workflow)

    def test_queue_snapshot_uses_watchdog_schedule_without_duplicate_workflow(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('    - cron: "*/15 * * * *"', workflow)
        self.assertIn("Export durable repository JSON queue snapshot", workflow)
        self.assertIn("automation/task_queue.json", workflow)
        self.assertFalse((ROOT / ".github" / "workflows" / "queue-snapshot-artifact.yml").exists())


if __name__ == "__main__":
    unittest.main()
