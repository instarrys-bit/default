import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCHDOG = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
AUTO_SYNC = ROOT / ".github" / "workflows" / "auto_sync.yml"


class ProductionQueueRoutingTests(unittest.TestCase):
    def test_watchdog_runs_have_unique_concurrency_groups(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        groups = re.findall(r"(?m)^\s+group:\s*(.+)$", workflow)
        self.assertGreaterEqual(len(groups), 3)
        self.assertEqual(len(groups), len(set(groups)))
        self.assertIn("github.run_id", workflow)
        self.assertIn("task-queue-supervision", workflow)
        queue_store = (ROOT / "storage" / "v2" / "queue_store.py").read_text(encoding="utf-8")
        self.assertIn("GitHubContentsJsonStore", queue_store)
        self.assertIn("sha", queue_store.lower())

    def test_queue_supervision_checks_relevant_predecessors(self):
        workflow = WATCHDOG.read_text(encoding="utf-8")
        queue_job = workflow.split("  task-queue-supervision:", 1)[1]
        self.assertIn("needs: [health-check]", queue_job)
        self.assertIn("needs.health-check.result == 'success'", queue_job)
        self.assertIn("group: shadowrocket-watchdog-queue-writer-main", queue_job)
        self.assertIn("actions: write", queue_job)
        self.assertIn("contents: write", queue_job)
        self.assertNotIn("group: shadowrocket-main-writer", queue_job)
        self.assertIn("task_scheduler.py", queue_job)
        self.assertIn("--max-tasks 1 run-once", queue_job)

    def test_all_stale_audit_checks_use_the_same_queue_aware_base_guard(self):
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        production = AUTO_SYNC.read_text(encoding="utf-8")
        self.assertNotIn("  stale-run-watch:", watchdog)
        self.assertNotIn("  manifest-integrity:", watchdog)
        self.assertIn("Stop stale audit before discovery and source downloads", production)
        self.assertIn("Stop stale audit before expensive deterministic review", production)
        self.assertIn("verify_publish_base.sh", production)
        self.assertIn("Independently verify committed remote rulesets", production)

    def test_superseded_audit_is_replaced_only_when_inputs_advanced(self):
        intent = (ROOT / "scripts" / "production_intent.py").read_text(encoding="utf-8")
        scheduler = (ROOT / "scripts" / "task_scheduler.py").read_text(encoding="utf-8")
        self.assertIn("def active_production_fingerprints", intent)
        self.assertIn('resource_lease.get("status") == "RELEASED"', intent)
        self.assertIn("expires_at <= now", intent)
        self.assertIn("supersede_stale_queued_production_tasks", scheduler)
        self.assertIn("cancel_stale_predecessor_tasks", scheduler)
        self.assertIn("Stop stale audit before discovery and source downloads",
                      AUTO_SYNC.read_text(encoding="utf-8"))

    def test_retired_request_intake_is_not_a_production_dependency(self):
        self.assertFalse((ROOT / ".github" / "workflows" / "request-intake.yml").exists())
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        programs = {item["id"] for item in registry["programs"]}
        self.assertNotIn("workflow_request_intake", programs)
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        self.assertNotIn("workflow_request_intake", {item["target_program_id"] for item in adapters["adapters"]})
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("enqueue-auto-sync", watchdog)
        production_inputs = json.loads((ROOT / "automation" / "production_inputs.json").read_text(encoding="utf-8"))
        self.assertIn(".github/workflows/request-intake.yml", production_inputs["non_production_path_patterns"])
        self.assertTrue((ROOT / "scripts" / "import_request_observations.py").exists())

    def test_auto_sync_requires_a_matching_persisted_watchdog_task(self):
        workflow = AUTO_SYNC.read_text(encoding="utf-8")
        inputs = workflow.split("automation_task_id:", 1)[1].split("baseline_source_event:", 1)[0]
        self.assertIn("required: true", inputs)
        self.assertIn("Verify Watchdog-owned durable task dispatch", workflow)
        self.assertIn("dispatch_intent", workflow)
        self.assertIn('durable_value = task_input.get(field, "")', workflow)
        self.assertIn("if durable_value != supplied:", workflow)
        self.assertNotIn("if supplied and task_input.get(field) != supplied:", workflow)
        self.assertIn('task.get("requester_program_id") != "workflow_automation_watchdog"', workflow)
        self.assertIn('task.get("status") not in {"CLAIMED", "VERIFYING"}', workflow)
        self.assertIn('task.get("requester_program_id") != "workflow_automation_watchdog"', workflow)
        self.assertIn('stream.write(f"AUTOMATION_TASK_ID_BASE={task_id}\\n")', workflow)
        self.assertIn('--task-id "$AUTOMATION_TASK_ID_BASE"', workflow)
        self.assertNotIn('--task-id "$AUTOMATION_TASK_ID" --proof-json', workflow)
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "workflow_auto_sync")
        correlation_input = next(item for item in adapter["workflow"]["inputs"] if item["name"] == "automation_task_id")
        self.assertTrue(correlation_input["required"])


if __name__ == "__main__":
    unittest.main()
