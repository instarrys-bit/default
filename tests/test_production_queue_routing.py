import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"
REQUEST_INTAKE = ROOT / ".github" / "workflows" / "request-intake.yml"


class ProductionQueueRoutingTests(unittest.TestCase):
    def test_watchdog_runs_have_unique_concurrency_groups(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("group: shadowrocket-automation-watchdog-", workflow)
        self.assertIn("github.run_id", workflow)
        self.assertIn("Queue writes use CAS", workflow)

    def test_queue_supervision_checks_relevant_predecessors(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("needs: [health-check, stale-run-watch, manifest-integrity]", workflow)
        self.assertIn("needs.stale-run-watch.result == 'success'", workflow)
        self.assertIn("needs.manifest-integrity.result == 'success' || needs.manifest-integrity.result == 'skipped'", workflow)

    def test_superseded_audit_is_replaced_only_when_inputs_advanced(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn('case "$SOURCE_CONCLUSION" in', workflow)
        self.assertIn('if [ "$SOURCE_SHA" = "$current_sha" ]', workflow)
        self.assertIn("Same-SHA deterministic failure requires diagnosis", workflow)
        self.assertIn('recovery_kind="superseded_inputs"', workflow)
        self.assertIn('idempotency_key="auto-sync-superseded:$SOURCE_RUN_ID"', workflow)
        self.assertIn("bash scripts/verify_publish_base.sh --check-only", workflow)

    def test_observation_intake_dispatches_watchdog_not_auto_sync(self):
        workflow = REQUEST_INTAKE.read_text(encoding="utf-8")
        self.assertIn("gh workflow run automation-watchdog.yml", workflow)
        self.assertNotIn("gh workflow run auto_sync.yml", workflow)
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        programs = {item["id"]: item for item in registry["programs"]}
        self.assertEqual(programs["workflow_request_intake"]["dispatches"], ["workflow_automation_watchdog"])
        self.assertIn("workflow_auto_sync", programs["workflow_automation_watchdog"]["dispatches"])

    def test_auto_sync_requires_a_matching_persisted_watchdog_task(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        inputs = workflow.split("automation_task_id:", 1)[1].split("baseline_source_event:", 1)[0]
        self.assertIn("required: true", inputs)
        self.assertIn("Verify Watchdog-owned durable task dispatch", workflow)
        self.assertIn("dispatch_intent", workflow)
        self.assertIn('task.get("requester_program_id") != "workflow_automation_watchdog"', workflow)
        self.assertIn('task.get("status") not in {"CLAIMED", "VERIFYING"}', workflow)
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "workflow_auto_sync")
        correlation_input = next(item for item in adapter["workflow"]["inputs"] if item["name"] == "automation_task_id")
        self.assertTrue(correlation_input["required"])


if __name__ == "__main__":
    unittest.main()
