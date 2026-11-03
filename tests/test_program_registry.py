import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_program_registry import validate_registry


class ProgramRegistryTests(unittest.TestCase):
    def make_repo(self, dependency=True):
        root = Path(tempfile.mkdtemp())
        (root / "scripts").mkdir()
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "automation").mkdir()
        (root / "scripts" / "alpha.py").write_text("print('alpha')\n", encoding="utf-8")
        (root / ".github" / "workflows" / "run.yml").write_text(
            "steps:\n  - run: python scripts/alpha.py\n", encoding="utf-8"
        )
        payload = {
            "schema_version": 1,
            "registry_policy": {
                "purpose": "test",
                "registration_required_for": "test",
                "collaboration_rule": "test",
                "permission_rule": "test",
                "activation_rule": "test",
            },
            "programs": [
                {
                    "id": "script_alpha",
                    "path": "scripts/alpha.py",
                    "kind": "python_component",
                    "responsibility": "test alpha",
                    "capabilities": ["test"],
                    "invocation": "python_cli",
                    "inputs": ["test"],
                    "outputs": ["test"],
                    "depends_on": [],
                    "dispatches": [],
                    "permission_boundary": "test",
                    "health_check": "test",
                    "orchestration": {"enabled": False, "allowed_callers": [], "max_attempts": 0, "timeout_seconds": 300},
                },
                {
                    "id": "workflow_run",
                    "path": ".github/workflows/run.yml",
                    "kind": "github_actions_workflow",
                    "responsibility": "test workflow",
                    "capabilities": ["test"],
                    "invocation": "test",
                    "inputs": ["test"],
                    "outputs": ["test"],
                    "depends_on": ["script_alpha"] if dependency else [],
                    "dispatches": [],
                    "permission_boundary": "test",
                    "health_check": "test",
                    "orchestration": {"enabled": False, "allowed_callers": [], "max_attempts": 0, "timeout_seconds": 300},
                },
            ],
        }
        registry = root / "automation" / "program_registry.json"
        registry.write_text(json.dumps(payload), encoding="utf-8")
        return root, registry

    def test_repository_registry_is_valid(self):
        result = validate_registry(ROOT)
        self.assertTrue(result["valid"])
        self.assertGreater(result["program_count"], 0)

    def test_accepts_registered_program_and_declared_workflow_dependency(self):
        root, registry = self.make_repo()
        result = validate_registry(root, registry)
        self.assertEqual(result["program_count"], 2)

    def test_rejects_new_program_without_registration(self):
        root, registry = self.make_repo()
        (root / "scripts" / "new_program.py").write_text("pass\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unregistered program files"):
            validate_registry(root, registry)

    def test_rejects_unregistered_nested_program(self):
        root, registry = self.make_repo()
        nested = root / "scripts" / "nested"
        nested.mkdir()
        (nested / "new_component.py").write_text("pass\\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unregistered program files"):
            validate_registry(root, registry)

    def test_accepts_workflow_dispatch_delegated_to_durable_scheduler(self):
        root, registry = self.make_repo()
        workflow_path = root / ".github" / "workflows" / "run.yml"
        workflow_path.write_text(
            "steps:\\n  - run: python scripts/alpha.py\\n  - run: enqueue-auto-sync\\n",
            encoding="utf-8",
        )
        target_path = root / ".github" / "workflows" / "auto_sync.yml"
        target_path.write_text("on:\\n  workflow_dispatch:\\n", encoding="utf-8")
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["programs"][1]["dispatches"] = ["workflow_auto_sync"]
        payload["programs"].append({
            "id": "workflow_auto_sync",
            "path": ".github/workflows/auto_sync.yml",
            "kind": "github_actions_workflow",
            "responsibility": "test audit target",
            "capabilities": ["deterministic_audit"],
            "invocation": "durable scheduler",
            "inputs": [],
            "outputs": [],
            "depends_on": [],
            "dispatches": [],
            "permission_boundary": "test",
            "health_check": "test",
            "orchestration": {
                "enabled": False, "allowed_callers": [],
                "max_attempts": 0, "timeout_seconds": 300,
            },
        })
        registry.write_text(json.dumps(payload), encoding="utf-8")
        result = validate_registry(root, registry)
        self.assertEqual(result["program_count"], 3)

    def test_rejects_workflow_call_without_declared_dependency(self):
        root, registry = self.make_repo(dependency=False)
        with self.assertRaisesRegex(ValueError, "script dependency mismatch"):
            validate_registry(root, registry)

    def test_rejects_orchestration_without_allowed_callers(self):
        root, registry = self.make_repo()
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["programs"][0]["orchestration"]["enabled"] = True
        registry.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "without explicit allowed callers"):
            validate_registry(root, registry)

    def test_rejects_unknown_orchestration_caller(self):
        root, registry = self.make_repo()
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["programs"][0]["orchestration"] = {
            "enabled": True, "allowed_callers": ["script_missing"],
            "max_attempts": 1, "timeout_seconds": 300,
        }
        registry.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unknown callers"):
            validate_registry(root, registry)

    def test_rejects_duplicate_program_ids(self):
        root, registry = self.make_repo()
        payload = json.loads(registry.read_text(encoding="utf-8"))
        payload["programs"][1]["id"] = "script_alpha"
        registry.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate program id"):
            validate_registry(root, registry)


if __name__ == "__main__":
    unittest.main()
