import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_execution_adapters import validate_execution_adapters


class ExecutionAdapterTests(unittest.TestCase):
    def make_repo(self):
        root = Path(tempfile.mkdtemp())
        (root / "automation").mkdir()
        (root / "scripts").mkdir()
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "scripts" / "worker.py").write_text("print('ok')\n", encoding="utf-8")
        workflow = root / ".github" / "workflows" / "run.yml"
        workflow.write_text(
            "run-name: Automation task \${{ inputs.automation_task_id || 'manual' }}\n"
            "on:\n  workflow_dispatch:\n    inputs:\n"
            "      item:\n        required: true\n        type: string\n"
            "      automation_task_id:\n        required: false\n        type: string\n"
            "jobs: {}\n",
            encoding="utf-8",
        )
        reg = {"programs": [
            {"id": "script_worker", "path": "scripts/worker.py", "kind": "python_component",
             "orchestration": {"enabled": False, "allowed_callers": [], "max_attempts": 0, "timeout_seconds": 300}},
            {"id": "workflow_run", "path": ".github/workflows/run.yml", "kind": "github_actions_workflow",
             "orchestration": {"enabled": False, "allowed_callers": [], "max_attempts": 0, "timeout_seconds": 300}},
        ]}
        doc = {
            "schema_version": 1,
            "policy": {
                "deny_by_default": True, "all_adapters_disabled_by_default": True,
                "shell_execution": "prohibited",
                "protected_config": "No adapter may modify modules/uu.conf.",
                "permission_rule": "least privilege", "completion_rule": "independent verification",
            },
            "adapters": [
                {"target_program_id": "script_worker", "target_kind": "python_component",
                 "adapter_type": "python_cli", "enabled": False, "interface_status": "unreviewed",
                 "allowed_callers": [], "entrypoint": {"path": "scripts/worker.py", "executable": "python3",
                 "argv_template": [], "shell": False}, "input_contract": None, "output_contract": None,
                 "timeout_seconds": 300, "retry": {"max_attempts": 0},
                 "completion": {"independent_verification_required": True}},
                {"target_program_id": "workflow_run", "target_kind": "github_actions_workflow",
                 "adapter_type": "github_actions_workflow", "enabled": False,
                 "interface_status": "workflow_dispatch_reviewed", "allowed_callers": [],
                 "workflow": {"path": ".github/workflows/run.yml", "dispatchable": True,
                 "inputs": [{"name": "item", "type": "string", "required": True},
                            {"name": "automation_task_id", "type": "string", "required": False}],
                 "allowed_refs": ["main"], "caller_permissions_required": ["actions:write", "contents:write"]},
                 "timeout_seconds": 300, "retry": {"max_attempts": 0},
                 "completion": {"independent_verification_required": True}},
            ],
        }
        rp = root / "automation" / "program_registry.json"
        ap = root / "automation" / "execution_adapters.json"
        rp.write_text(json.dumps(reg), encoding="utf-8")
        ap.write_text(json.dumps(doc), encoding="utf-8")
        return root, ap, rp, doc

    def test_repository_contract_is_valid(self):
        result = validate_execution_adapters(ROOT)
        self.assertTrue(result["valid"])
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        self.assertEqual(result["adapter_count"], len(adapters["adapters"]))
        self.assertEqual(result["enabled_adapter_count"], 2)
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        adapters = json.loads((ROOT / "automation" / "execution_adapters.json").read_text(encoding="utf-8"))
        enabled = [item["target_program_id"] for item in adapters["adapters"] if item["enabled"]]
        self.assertEqual(enabled, ["script_assess_sources", "workflow_auto_sync", "workflow_self_healing_tests"])
        program = next(item for item in registry["programs"] if item["id"] == "workflow_self_healing_tests")
        adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "workflow_self_healing_tests")
        self.assertEqual(program["orchestration"]["allowed_callers"], ["workflow_automation_watchdog"])
        self.assertEqual(adapter["allowed_callers"], ["workflow_automation_watchdog"])
        self.assertEqual(program["orchestration"]["max_attempts"], 1)
        self.assertEqual(adapter["retry"]["max_attempts"], 0)
        audit_program = next(item for item in registry["programs"] if item["id"] == "workflow_auto_sync")
        audit_adapter = next(item for item in adapters["adapters"] if item["target_program_id"] == "workflow_auto_sync")
        self.assertEqual(audit_program["orchestration"]["allowed_callers"], ["workflow_automation_watchdog"])
        self.assertEqual(audit_adapter["allowed_callers"], ["workflow_automation_watchdog"])
        self.assertEqual(audit_program["orchestration"]["max_attempts"], 2)
        self.assertEqual(audit_adapter["retry"]["max_attempts"], 1)

    def test_valid_minimal_inventory(self):
        root, ap, rp, _ = self.make_repo()
        self.assertEqual(validate_execution_adapters(root, ap, rp)["adapter_count"], 2)

    def test_rejects_missing_target(self):
        root, ap, rp, doc = self.make_repo()
        doc["adapters"].pop()
        ap.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "adapter inventory mismatch"):
            validate_execution_adapters(root, ap, rp)

    def test_rejects_shell(self):
        root, ap, rp, doc = self.make_repo()
        doc["adapters"][0]["entrypoint"]["shell"] = True
        ap.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "without shell"):
            validate_execution_adapters(root, ap, rp)

    def test_rejects_dispatchable_workflow_without_unique_task_correlation(self):
        root, ap, rp, doc = self.make_repo()
        path = root / ".github" / "workflows" / "run.yml"
        path.write_text("\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines()
            if not line.startswith("run-name:")
        ) + "\n", encoding="utf-8")
        ap.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "automation_task_id"):
            validate_execution_adapters(root, ap, rp)

    def test_rejects_workflow_caller_without_queue_storage_permission(self):
        root, ap, rp, doc = self.make_repo()
        doc["adapters"][1]["workflow"]["caller_permissions_required"] = ["actions:write"]
        ap.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "actions:write and contents:write"):
            validate_execution_adapters(root, ap, rp)

    def test_rejects_invalid_resource_lease_contract(self):
        root, ap, rp, doc = self.make_repo()
        doc["adapters"][0]["resource_contract"] = {
            "mode": "shared", "fencing_required": False,
            "resource_keys": ["../unsafe"], "lease_seconds": 60,
        }
        ap.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "resource_contract"):
            validate_execution_adapters(root, ap, rp)

    def test_rejects_workflow_input_drift(self):
        root, ap, rp, doc = self.make_repo()
        doc["adapters"][1]["workflow"]["inputs"] = []
        ap.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "workflow_dispatch contract drift"):
            validate_execution_adapters(root, ap, rp)


if __name__ == "__main__":
    unittest.main()
