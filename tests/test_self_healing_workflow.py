import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
AUTO_SYNC = WORKFLOWS / "auto_sync.yml"
WATCHDOG = WORKFLOWS / "automation-watchdog.yml"
STORAGE = WORKFLOWS / "storage-management.yml"


class AutomationIncidentRecoveryTests(unittest.TestCase):
    def test_exactly_four_workflows_remain(self):
        self.assertEqual(sorted(p.name for p in WORKFLOWS.glob("*.yml")), [
            "auto_sync.yml", "automation-watchdog.yml", "dashboard-pages.yml", "storage-management.yml"
        ])

    def test_failure_record_uses_storage_management_input_contract(self):
        auto = AUTO_SYNC.read_text(encoding="utf-8")
        storage = STORAGE.read_text(encoding="utf-8")
        block = auto.split("  notify-failure:", 1)[1].split("  resolve-failure:", 1)[0]
        self.assertIn("-f operation=record", block)
        self.assertIn("-f automation_task_id=", block)
        self.assertIn("-f run_id=", block)
        self.assertIn("-f source_sha=", block)
        self.assertIn("-f classification=PIPELINE_FAILURE", block)
        self.assertIn("-f run_url=", block)
        self.assertNotIn("-f workflow=", block)
        self.assertNotIn("-f event_id=", block)
        for field in ("operation", "automation_task_id", "run_id", "source_sha", "classification", "summary", "run_url"):
            self.assertIn(field + ":", storage)

    def test_incident_closure_requires_all_pipeline_gates(self):
        auto = AUTO_SYNC.read_text(encoding="utf-8")
        block = auto.split("  resolve-failure:", 1)[1].split("  watchdog-reconciliation:", 1)[0]
        self.assertIn("needs: [audit, preflight, publish]", block)
        self.assertIn("needs.preflight.result == 'success'", block)
        self.assertIn("-f automation_task_id=", block)
        self.assertNotIn("-f event_id=", block)

    def test_watchdog_wakeup_uses_its_real_dispatch_contract(self):
        auto = AUTO_SYNC.read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        block = auto.split("  watchdog-reconciliation:", 1)[1]
        self.assertIn("'{ref:$ref}'", block)
        self.assertNotIn("production_producer_run_id", block)
        self.assertIn("workflow_dispatch:", watchdog)
        self.assertIn("Automation watchdog / ${{ github.run_id }}", watchdog)

    def test_protected_user_config_is_never_a_production_write_target(self):
        control = json.loads((ROOT / "automation" / "production_control.json").read_text(encoding="utf-8"))
        self.assertEqual(control["policy"]["protected_config"], "modules/uu.conf remains read-only")
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        for adapter in adapters["adapters"]:
            self.assertNotIn("modules/uu.conf", adapter.get("write_resources", []))
            self.assertNotIn("modules/uu.conf", adapter.get("publish_resources", []))


if __name__ == "__main__":
    unittest.main()
