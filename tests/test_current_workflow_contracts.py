import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class CurrentWorkflowContractTests(unittest.TestCase):
    def test_repository_keeps_exactly_four_workflow_entrypoints(self):
        names = {p.name for p in WORKFLOWS.glob("*.yml")}
        self.assertEqual(names, {
            "auto_sync.yml",
            "automation-watchdog.yml",
            "dashboard-pages.yml",
            "storage-management.yml",
        })

    def test_failure_and_recovery_dispatches_use_declared_storage_inputs(self):
        auto = (WORKFLOWS / "auto_sync.yml").read_text(encoding="utf-8")
        storage = (WORKFLOWS / "storage-management.yml").read_text(encoding="utf-8")
        failure = auto.split("  notify-failure:", 1)[1].split("  resolve-failure:", 1)[0]
        recovery = auto.split("  resolve-failure:", 1)[1].split("  watchdog-reconciliation:", 1)[0]
        self.assertIn("-f operation=record", failure)
        self.assertIn("-f automation_task_id=", failure)
        self.assertNotIn("-f workflow=", failure)
        self.assertNotIn("-f event_id=", failure)
        self.assertIn("-f operation=resolve", recovery)
        self.assertIn("-f automation_task_id=", recovery)
        self.assertNotIn("-f workflow=", recovery)
        self.assertNotIn("-f event_id=", recovery)
        self.assertIn("      automation_task_id:", storage)
        self.assertNotIn("      workflow_key:", storage)
        self.assertIn("WORKFLOW_KEY: ${{ startsWith(inputs.automation_task_id, 'auto-sync-') && 'auto_sync' || 'automation_watchdog' }}", storage)
        self.assertIn('automation_task_id="auto-sync-failure-$RUN_ID"', failure)
        self.assertIn('automation_task_id="auto-sync-recovery-$RUN_ID"', recovery)
        self.assertIn("      operation:", storage)
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        storage_program = next(item for item in registry["programs"] if item["id"] == "workflow_storage_management")
        storage_adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "workflow_storage_management")
        self.assertEqual(storage_program["inputs"], [item["name"] for item in storage_adapter["workflow"]["inputs"]])

    def test_incident_recovery_requires_preflight_audit_and_publish_success(self):
        auto = (WORKFLOWS / "auto_sync.yml").read_text(encoding="utf-8")
        recovery = auto.split("  resolve-failure:", 1)[1].split("  watchdog-reconciliation:", 1)[0]
        self.assertIn("needs: [preflight, audit, publish]", recovery)
        self.assertIn("needs.preflight.result == 'success'", recovery)
        self.assertIn("needs.audit.result == 'success'", recovery)
        self.assertIn("needs.publish.result == 'success'", recovery)

    def test_watchdog_wake_is_a_valid_no_input_dispatch(self):
        auto = (WORKFLOWS / "auto_sync.yml").read_text(encoding="utf-8")
        wake = auto.split("  watchdog-reconciliation:", 1)[1]
        self.assertIn("payload='{\\"ref\\":\\"main\\"}'", wake)
        self.assertNotIn("production_producer_run_id", wake)

    def test_scheduler_owns_recovery_and_pending_result_verification(self):
        watchdog = (WORKFLOWS / "automation-watchdog.yml").read_text(encoding="utf-8")
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertNotIn("recover-expired || true", watchdog)
        self.assertIn("--max-tasks 1 run-once", watchdog)
        run_once = scheduler.split("def run_scheduler_once", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("recover_remote(store, registry, initial_now)", run_once)
        self.assertIn("verify_pending_remote(store, registry, adapters, initial_now)", run_once)


if __name__ == "__main__":
    unittest.main()
