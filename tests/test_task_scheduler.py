import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import enqueue_remote
from task_queue_runtime import now_utc
from task_scheduler import run_scheduler_once, build_execution_plan


class MemoryStore:
    def __init__(self):
        self.document = {"schema_version": 1, "revision": 0, "tasks": []}
        self.writes = 0

    def mutate(self, mutator, max_conflicts=5):
        candidate, result = mutator(json.loads(json.dumps(self.document)))
        if candidate != self.document:
            self.document = candidate
            self.writes += 1
        return result

    def read(self):
        return type("Snapshot", (), {"document": json.loads(json.dumps(self.document)), "content_sha": "fake-sha"})()


class TaskSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "scripts").mkdir()
        (self.root / "shadowrocket").mkdir()
        (self.root / "shadowrocket" / "ss.conf").write_text("[General]\n", encoding="utf-8")
        self.script = self.root / "scripts" / "target.py"
        self.script.write_text(
            "import json, os, sys\n"
            "payload=json.load(open(sys.argv[1], encoding='utf-8'))\n"
            "print(json.dumps({'ok': True, 'value': payload['value'], "
            "'token_visible': 'GITHUB_TOKEN' in os.environ}))\n",
            encoding="utf-8",
        )
        self.store = MemoryStore()
        self.registry = {"programs": [
            {"id": "script_requester", "path": "scripts/requester.py",
             "kind": "python_component", "capabilities": ["request"],
             "orchestration": {"enabled": False, "allowed_callers": [],
                               "max_attempts": 0, "timeout_seconds": 300}},
            {"id": "script_target", "path": "scripts/target.py",
             "kind": "python_component", "capabilities": ["test_capability"],
             "orchestration": {"enabled": True, "allowed_callers": ["script_requester"],
                               "max_attempts": 2, "timeout_seconds": 120}},
            {"id": "script_task_result_verifier", "path": "scripts/task_result_verifier.py",
             "kind": "python_component", "capabilities": ["task_result_verification"],
             "orchestration": {"enabled": False, "allowed_callers": [],
                               "max_attempts": 0, "timeout_seconds": 300}},
        ]}
        self.input_schema = {
            "type": "object", "required": ["value"],
            "properties": {"value": {"type": "integer"}},
            "additionalProperties": False,
        }
        self.output_schema = {
            "type": "object", "required": ["ok", "value", "token_visible"],
            "properties": {
                "ok": {"type": "boolean", "const": True},
                "value": {"type": "integer"},
                "token_visible": {"type": "boolean", "const": False},
            },
            "additionalProperties": False,
        }
        self.adapters = {"schema_version": 1, "adapters": [
            {"target_program_id": "script_requester", "target_kind": "python_component",
             "adapter_type": "python_cli", "enabled": False, "interface_status": "unreviewed",
             "allowed_callers": [], "entrypoint": {"path": "scripts/requester.py",
             "executable": "python3", "argv_template": [], "shell": False},
             "input_contract": None, "output_contract": None, "timeout_seconds": 30,
             "retry": {"max_attempts": 0}, "completion": {"independent_verification_required": True}},
            {"target_program_id": "script_target", "target_kind": "python_component",
             "adapter_type": "python_cli", "enabled": True, "interface_status": "reviewed",
             "allowed_callers": ["script_requester"],
             "entrypoint": {"path": "scripts/target.py", "executable": "python3",
                            "argv_template": ["{task_input_file}"], "shell": False},
             "input_contract": self.input_schema, "output_contract": self.output_schema,
             "timeout_seconds": 30, "retry": {"max_attempts": 2},
             "completion": {"independent_verification_required": True}},
            {"target_program_id": "script_task_result_verifier", "target_kind": "python_component",
             "adapter_type": "python_cli", "enabled": False, "interface_status": "unreviewed",
             "allowed_callers": [], "entrypoint": {"path": "scripts/task_result_verifier.py",
             "executable": "python3", "argv_template": [], "shell": False},
             "input_contract": None, "output_contract": None, "timeout_seconds": 30,
             "retry": {"max_attempts": 0}, "completion": {"independent_verification_required": True}},
        ]}
        self.now = now_utc()

    def enqueue(self, payload=None):
        return enqueue_remote({
            "idempotency_key": "scheduler:test:once",
            "requester_program_id": "script_requester",
            "target_program_id": "script_target",
            "capability": "test_capability",
            "input": payload if payload is not None else {"value": 7},
        }, self.store, self.registry, self.now)

    def test_reviewed_python_adapter_executes_and_is_independently_verified(self):
        task = self.enqueue()["task"]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "must-not-reach-child"}):
            report = run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="scheduler-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.assertEqual(report["processed_count"], 1)
        saved = self.store.document["tasks"][0]
        self.assertEqual(saved["task_id"], task["task_id"])
        self.assertEqual(saved["status"], "SUCCEEDED")
        self.assertEqual(saved["result"]["value"], 7)
        self.assertFalse(saved["result"]["token_visible"])
        self.assertEqual(saved["verification"]["status"], "passed")

    def test_disabled_adapter_is_reported_but_never_claimed(self):
        self.enqueue()
        self.adapters["adapters"][1]["enabled"] = False
        self.adapters["adapters"][1]["interface_status"] = "unreviewed"
        report = run_scheduler_once(
            self.store, self.registry, self.adapters,
            worker_id="scheduler-test", root=self.root, now=self.now,
        )
        self.assertEqual(report["processed_count"], 0)
        self.assertEqual(self.store.document["tasks"][0]["status"], "QUEUED")
        self.assertIn("disabled", report["blocked"][0]["reason"])

    def test_invalid_input_contract_blocks_before_claim(self):
        self.enqueue({"value": "wrong-type"})
        plan = build_execution_plan(self.store.document, self.registry, self.adapters, self.root, self.now)
        self.assertEqual(plan["eligible_task_ids"], [])
        self.assertIn("input contract failed", plan["blocked"][0]["reason"])
        self.assertEqual(self.store.document["tasks"][0]["status"], "QUEUED")

    def test_child_modification_of_protected_config_stops_scheduler(self):
        self.script.write_text(
            "import json\n"
            "from pathlib import Path\n"
            "Path('shadowrocket/ss.conf').write_text('changed', encoding='utf-8')\n"
            "print(json.dumps({'ok': True, 'value': 7, 'token_visible': False}))\n",
            encoding="utf-8",
        )
        self.enqueue()
        with self.assertRaisesRegex(RuntimeError, "scheduler stopped fail-closed"):
            run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="scheduler-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.assertNotEqual((self.root / "shadowrocket" / "ss.conf").read_text(encoding="utf-8"), "[General]\n")

    def test_shell_execution_and_unreviewed_placeholders_are_rejected(self):
        self.adapters["adapters"][1]["entrypoint"]["shell"] = True
        self.enqueue()
        plan = build_execution_plan(self.store.document, self.registry, self.adapters, self.root, self.now)
        self.assertEqual(plan["eligible_task_ids"], [])
        self.assertIn("prohibit shell execution", plan["blocked"][0]["reason"])
        self.adapters["adapters"][1]["entrypoint"]["shell"] = False
        self.adapters["adapters"][1]["entrypoint"]["argv_template"] = ["{untrusted}"]
        plan = build_execution_plan(self.store.document, self.registry, self.adapters, self.root, self.now)
        self.assertIn("unsupported placeholder", plan["blocked"][0]["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
