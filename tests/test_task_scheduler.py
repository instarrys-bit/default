import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import claim_remote, enqueue_remote
from task_queue_runtime import now_utc
from task_scheduler import run_scheduler_once, build_execution_plan, enqueue_source_assessment_task


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
            "parent_env=open(f'/proc/{os.getppid()}/environ','rb').read()\n"
            "token_visible=('GITHUB_TOKEN' in os.environ or b'GITHUB_TOKEN=' in parent_env)\n"
            "print(json.dumps({'ok': True, 'value': payload['value'], 'token_visible': token_visible}))\n",
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

    def test_source_assessment_enqueue_requires_enabled_watchdog_capability_and_pins_predecessor(self):
        source_root = self.root
        (source_root / "sources").mkdir(exist_ok=True)
        artifact = source_root / "sources" / "discovered_sources.json"
        artifact.write_text('{"candidates":[]}\\n', encoding="utf-8")
        registry = {"programs": [
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {"id": "script_assess_sources", "capabilities": ["source_assessment"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 1, "timeout_seconds": 480}},
        ]}
        schema = {
            "type": "object",
            "required": ["max_urls", "max_file_bytes", "max_total_bytes", "predecessor"],
            "properties": {
                "max_urls": {"type": "integer", "minimum": 1, "maximum": 20},
                "max_file_bytes": {"type": "integer", "minimum": 1, "maximum": 1000000},
                "max_total_bytes": {"type": "integer", "minimum": 1, "maximum": 10000000},
                "predecessor": {"type": "object"},
            },
            "additionalProperties": False,
        }
        adapters = {"adapters": [{
            "target_program_id": "script_assess_sources", "enabled": True,
            "adapter_type": "python_cli", "interface_status": "reviewed",
            "input_contract": schema,
        }]}
        from task_scheduler import read_only_resource_digests
        digest = read_only_resource_digests(source_root, ["sources/discovered_sources.json"])["sources/discovered_sources.json"]
        payload = {
            "max_urls": 1, "max_file_bytes": 1000000, "max_total_bytes": 1000000,
            "predecessor": {
                "program_id": "script_discover_sources",
                "workflow_name": "Shadowrocket Deterministic Domain Audit (User Config Baseline)",
                "workflow_run_id": "41770000000",
                "workflow_head_sha": "a" * 40,
                "artifact_path": "sources/discovered_sources.json",
                "artifact_sha256": digest,
            },
        }
        first = enqueue_source_assessment_task(
            self.store, registry, adapters,
            idempotency_key="source-assessment:41770000000",
            input_payload=payload, root=source_root,
        )
        second = enqueue_source_assessment_task(
            self.store, registry, adapters,
            idempotency_key="source-assessment:41770000000",
            input_payload=payload, root=source_root,
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertEqual(self.store.document["tasks"][0]["requester_program_id"], "workflow_automation_watchdog")
        self.assertEqual(self.store.document["tasks"][0]["target_program_id"], "script_assess_sources")

    def test_source_assessment_enqueue_rejects_stale_predecessor_digest(self):
        source_root = self.root
        (source_root / "sources").mkdir(exist_ok=True)
        (source_root / "sources" / "discovered_sources.json").write_text('{"candidates":[]}\\n', encoding="utf-8")
        registry = {"programs": [
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {"id": "script_assess_sources", "capabilities": ["source_assessment"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 1, "timeout_seconds": 480}},
        ]}
        adapters = {"adapters": [{
            "target_program_id": "script_assess_sources", "enabled": True,
            "adapter_type": "python_cli", "interface_status": "reviewed",
            "input_contract": {"type": "object", "required": ["predecessor"], "properties": {"predecessor": {"type": "object"}}},
        }]}
        payload = {"predecessor": {
            "program_id": "script_discover_sources",
            "workflow_name": "Shadowrocket Deterministic Domain Audit (User Config Baseline)",
            "workflow_run_id": "41770000001",
            "workflow_head_sha": "a" * 40,
            "artifact_path": "sources/discovered_sources.json",
            "artifact_sha256": "0" * 64,
        }}
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            enqueue_source_assessment_task(
                self.store, registry, adapters,
                idempotency_key="source-assessment:41770000001",
                input_payload=payload, root=source_root,
            )

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

    def test_scheduler_recovers_expired_leases_before_planning(self):
        task = self.enqueue()["task"]
        claim_remote(
            "worker-old", self.store, self.registry,
            eligible_task_ids={task["task_id"]}, now=self.now,
        )
        later = self.now + timedelta(seconds=121)
        report = run_scheduler_once(
            self.store, self.registry, self.adapters,
            worker_id="scheduler-test", max_tasks=1, root=self.root, now=later,
        )
        self.assertEqual(report["recovered_count"], 1)
        self.assertEqual(report["processed_count"], 0)
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
