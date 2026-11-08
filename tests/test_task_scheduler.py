import copy
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
from task_queue_runtime import now_utc, stamp, manual_authorization_record, validate_manual_authorization
from task_scheduler import run_scheduler_once, build_execution_plan, enqueue_source_assessment_task, enqueue_source_discovery_task, enqueue_auto_sync_task, assert_current_production_input, production_source_assessment_gate, supersede_stale_queued_production_tasks, generated_python_cache_paths, publishable_resource_path, validate_repository_write_scope


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
    def test_independent_production_gate_requires_latest_verified_non_activating_assessment(self):
        control = self.root / "automation" / "production_control.json"
        control.write_text(json.dumps({
            "schema_version": 1, "dispatch_mode": "enabled", "source_discovery_mode": "independent"
        }), encoding="utf-8")
        older = {
            "task_id": "task_" + "1" * 24, "target_program_id": "workflow_source_discovery",
            "status": "SUCCEEDED", "created_at": "2026-11-07T12:00:00Z",
            "result": {"run_evidence": {"run_id": 42373818238}},
        }
        older_assessment = {
            "task_id": "task_" + "2" * 24, "target_program_id": "script_assess_sources",
            "status": "SUCCEEDED",
            "created_at": "2026-11-07T12:30:00Z",
            "input": {"predecessor": {"workflow_run_id": "42373818238"}},
            "verification": {"status": "passed"},
            "result": {"artifact_verification": {"valid": True, "activation_count": 0}},
        }
        newer = {
            "task_id": "task_" + "3" * 24, "target_program_id": "workflow_source_discovery",
            "status": "VERIFYING", "created_at": "2026-11-08T12:00:00Z",
            "result": {"run_evidence": {"run_id": 42417075148}},
        }
        self.assertFalse(production_source_assessment_gate([older, older_assessment, newer], self.root))
        newer["status"] = "SUCCEEDED"
        self.assertFalse(production_source_assessment_gate([older, older_assessment, newer], self.root))
        latest_assessment = {
            "task_id": "task_" + "4" * 24, "target_program_id": "script_assess_sources",
            "status": "SUCCEEDED",
            "created_at": "2026-11-08T12:30:00Z",
            "input": {"predecessor": {"workflow_run_id": "42417075148"}},
            "verification": {"status": "passed"},
            "result": {"artifact_verification": {"valid": True, "activation_count": 0}},
        }
        self.assertTrue(production_source_assessment_gate(
            [older, older_assessment, newer, latest_assessment], self.root
        ))
        latest_assessment["result"]["artifact_verification"]["activation_count"] = 1
        self.assertFalse(production_source_assessment_gate(
            [older, older_assessment, newer, latest_assessment], self.root
        ))

    def test_source_discovery_daily_enqueue_is_idempotent(self):
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        first = enqueue_source_discovery_task(self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456")
        second = enqueue_source_discovery_task(self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456")
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["task_id"], second["task_id"])

    def test_source_discovery_revision_change_gets_a_new_daily_task(self):
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        first = enqueue_source_discovery_task(
            self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456"
        )
        refreshed = enqueue_source_discovery_task(
            self.store, registry, idempotency_key="source-discovery:2026-11-07:123456abcdef"
        )
        self.assertTrue(first["created"])
        self.assertTrue(refreshed["created"])
        self.assertNotEqual(first["task_id"], refreshed["task_id"])

    def test_source_discovery_recovery_requires_dead_letter_and_is_bounded(self):
        registry = json.loads((ROOT / "automation" / "program_registry.json").read_text(encoding="utf-8"))
        base = enqueue_source_discovery_task(self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456")
        with self.assertRaisesRegex(ValueError, "dead-lettered matching Discovery task"):
            enqueue_source_discovery_task(self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456:recovery:1")
        task = self.store.document["tasks"][0]
        task["status"] = "DEAD_LETTER"
        task["attempts"] = task["max_attempts"]
        task["last_error"] = {"type": "workflow_run_failed", "message": "resource lease expired"}
        task["state_history"] = ["QUEUED", "CLAIMED", "DEAD_LETTER"]
        recovery = enqueue_source_discovery_task(self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456:recovery:1")
        duplicate = enqueue_source_discovery_task(self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456:recovery:1")
        self.assertTrue(recovery["created"])
        self.assertFalse(duplicate["created"])
        self.assertEqual(recovery["task_id"], duplicate["task_id"])
        with self.assertRaisesRegex(ValueError, "requires a UTC-day key"):
            enqueue_source_discovery_task(self.store, registry, idempotency_key="source-discovery:2026-11-07:abcdef123456:recovery:2")

    def test_generated_python_cache_paths_are_discarded_from_artifact_sets(self):
        paths = [
            "scripts/__pycache__/task_scheduler.cpython-311.pyc",
            "scripts/__pycache__/nested/module.pyc",
            "sources/source_assessments.json",
            "reports/source-assessment.md",
        ]
        self.assertEqual(
            generated_python_cache_paths(paths),
            ["scripts/__pycache__/nested/module.pyc",
             "scripts/__pycache__/task_scheduler.cpython-311.pyc"],
        )

    def test_python_cache_paths_are_never_publishable_artifacts(self):
        resources = ["sources/source_assessments.json", "reports/source-assessment.md"]
        self.assertFalse(publishable_resource_path("scripts/__pycache__/task_scheduler.cpython-311.pyc", resources))
        self.assertFalse(publishable_resource_path("scripts/task_scheduler.pyc", resources))
        self.assertTrue(publishable_resource_path("sources/source_assessments.json", resources))

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "scripts").mkdir()
        (self.root / "modules").mkdir()
        (self.root / "modules" / "uu.conf").write_text("[General]\n", encoding="utf-8")
        (self.root / "automation").mkdir()
        (self.root / "automation" / "production_control.json").write_text(
            json.dumps({"schema_version": 1, "dispatch_mode": "enabled", "source_discovery_mode": "monolithic_fallback"}),
            encoding="utf-8",
        )
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
        adapters = {"schema_version": 1, "adapters": [{
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
                "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
                "workflow_run_id": "41770000000",
                "workflow_head_sha": "a" * 40,
                "artifact_path": "sources/discovered_sources.json",
                "artifact_sha256": digest,
            },
        }
        first = enqueue_source_assessment_task(
            self.store, registry, adapters,
            idempotency_key="source-assessment:41770000000:parser-v2",
            input_payload=payload, root=source_root,
        )
        second = enqueue_source_assessment_task(
            self.store, registry, adapters,
            idempotency_key="source-assessment:41770000000:parser-v2",
            input_payload=payload, root=source_root,
        )
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertEqual(self.store.document["tasks"][0]["requester_program_id"], "workflow_automation_watchdog")
        self.assertEqual(self.store.document["tasks"][0]["target_program_id"], "script_assess_sources")

    def test_source_assessment_dead_letter_gets_one_provenance_bound_recovery(self):
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
        adapters = {"schema_version": 1, "adapters": [{
            "target_program_id": "script_assess_sources", "enabled": True,
            "adapter_type": "python_cli", "interface_status": "reviewed",
            "input_contract": {"type": "object", "required": ["predecessor"],
                               "properties": {"predecessor": {"type": "object"}}},
        }]}
        from task_scheduler import read_only_resource_digests
        digest = read_only_resource_digests(source_root, ["sources/discovered_sources.json"])["sources/discovered_sources.json"]
        payload = {"max_urls": 1, "max_file_bytes": 1000000, "max_total_bytes": 1000000,
                   "predecessor": {
                       "program_id": "script_discover_sources",
                       "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
                       "workflow_run_id": "41770000002",
                       "workflow_head_sha": "b" * 40,
                       "artifact_path": "sources/discovered_sources.json",
                       "artifact_sha256": digest,
                   }}
        base = enqueue_source_assessment_task(
            self.store, registry, adapters,
            idempotency_key="source-assessment:41770000002:parser-v2",
            input_payload=payload, root=source_root,
        )
        self.store.document["tasks"][0]["status"] = "DEAD_LETTER"
        self.store.document["tasks"][0]["attempts"] = self.store.document["tasks"][0]["max_attempts"]
        self.store.document["tasks"][0]["state_history"].extend(["CLAIMED", "FAILED", "DEAD_LETTER"])
        self.store.document["tasks"][0]["last_error"] = {"type": "test_dead_letter"}
        self.store.document["revision"] += 1
        recovery = enqueue_source_assessment_task(
            self.store, registry, adapters,
            idempotency_key="source-assessment:41770000002:parser-v2:recovery:1",
            input_payload=payload, root=source_root,
        )
        self.assertTrue(recovery["created"])
        self.assertEqual(recovery["status"], "QUEUED")
        self.assertEqual(self.store.document["tasks"][1]["input"], payload)
        self.assertEqual(self.store.document["tasks"][1]["idempotency_key"],
                         "source-assessment:41770000002:parser-v2:recovery:1")
        with self.assertRaisesRegex(ValueError, "idempotency key must be bound"):
            enqueue_source_assessment_task(
                self.store, registry, adapters,
                idempotency_key="source-assessment:41770000002:parser-v2:recovery:2",
                input_payload=payload, root=source_root,
            )

    def test_source_assessment_recovery_requires_dead_lettered_base(self):
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
        adapters = {"schema_version": 1, "adapters": [{
            "target_program_id": "script_assess_sources", "enabled": True,
            "adapter_type": "python_cli", "interface_status": "reviewed",
            "input_contract": {"type": "object", "required": ["predecessor"],
                               "properties": {"predecessor": {"type": "object"}}},
        }]}
        from task_scheduler import read_only_resource_digests
        digest = read_only_resource_digests(source_root, ["sources/discovered_sources.json"])["sources/discovered_sources.json"]
        payload = {"predecessor": {
            "program_id": "script_discover_sources",
            "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
            "workflow_run_id": "41770000003",
            "workflow_head_sha": "c" * 40,
            "artifact_path": "sources/discovered_sources.json",
            "artifact_sha256": digest,
        }}
        enqueue_source_assessment_task(
            self.store, registry, adapters,
            idempotency_key="source-assessment:41770000003:parser-v2",
            input_payload=payload, root=source_root,
        )
        with self.assertRaisesRegex(ValueError, "requires its exact base task to be DEAD_LETTER"):
            enqueue_source_assessment_task(
                self.store, registry, adapters,
                idempotency_key="source-assessment:41770000003:parser-v2:recovery:1",
                input_payload=payload, root=source_root,
            )

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
        adapters = {"schema_version": 1, "adapters": [{
            "target_program_id": "script_assess_sources", "enabled": True,
            "adapter_type": "python_cli", "interface_status": "reviewed",
            "input_contract": {"type": "object", "required": ["predecessor"], "properties": {"predecessor": {"type": "object"}}},
        }]}
        payload = {"predecessor": {
            "program_id": "script_discover_sources",
            "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
            "workflow_run_id": "41770000001",
            "workflow_head_sha": "a" * 40,
            "artifact_path": "sources/discovered_sources.json",
            "artifact_sha256": "0" * 64,
        }}
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            enqueue_source_assessment_task(
                self.store, registry, adapters,
                idempotency_key="source-assessment:41770000001:parser-v2",
                input_payload=payload, root=source_root,
            )

    def test_typed_predecessor_digest_blocks_stale_discovery_snapshot(self):
        (self.root / "sources").mkdir(exist_ok=True)
        artifact = self.root / "sources" / "discovered_sources.json"
        artifact.write_text('{"candidates":[]}\\n', encoding="utf-8")
        from task_scheduler import read_only_resource_digests
        digest = read_only_resource_digests(self.root, ["sources/discovered_sources.json"])["sources/discovered_sources.json"]
        predecessor_schema = {
            "type": "object",
            "required": ["program_id", "workflow_name", "workflow_run_id", "workflow_head_sha", "artifact_path", "artifact_sha256"],
            "properties": {
                "program_id": {"type": "string", "const": "script_discover_sources"},
                "workflow_name": {"type": "string", "const": "Shadowrocket Source Discovery (Watchdog)"},
                "workflow_run_id": {"type": "string"},
                "workflow_head_sha": {"type": "string"},
                "artifact_path": {"type": "string", "const": "sources/discovered_sources.json"},
                "artifact_sha256": {"type": "string"},
            },
            "additionalProperties": False,
        }
        adapter = self.adapters["adapters"][1]
        adapter["input_contract"] = {"type": "object", "required": ["value", "predecessor"], "properties": {"value": {"type": "integer"}, "predecessor": predecessor_schema}, "additionalProperties": False}
        adapter["read_only_resources"] = ["sources/discovered_sources.json"]
        adapter["required_read_only_resources"] = ["sources/discovered_sources.json"]
        adapter["dependency_contract"] = {"predecessor_program_id": "script_discover_sources", "artifact_path": "sources/discovered_sources.json", "producer_workflow_name": "Shadowrocket Source Discovery (Watchdog)"}
        payload = {"value": 7, "predecessor": {"program_id": "script_discover_sources", "workflow_name": "Shadowrocket Source Discovery (Watchdog)", "workflow_run_id": "41770000000", "workflow_head_sha": "a" * 40, "artifact_path": "sources/discovered_sources.json", "artifact_sha256": digest}}
        enqueue_remote({"idempotency_key": "scheduler:typed-predecessor", "requester_program_id": "script_requester", "target_program_id": "script_target", "capability": "test_capability", "input": payload}, self.store, self.registry, self.now)
        plan = build_execution_plan(self.store.document, self.registry, self.adapters, self.root, self.now)
        self.assertEqual(len(plan["eligible_task_ids"]), 1)
        artifact.write_text('{"candidates":[{"url":"changed"}]}\\n', encoding="utf-8")
        plan = build_execution_plan(self.store.document, self.registry, self.adapters, self.root, self.now)
        self.assertEqual(plan["eligible_task_ids"], [])
        self.assertIn("digest changed", plan["blocked"][0]["reason"])

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

    def test_hold_stops_scheduler_before_recovery_verification_or_claim(self):
        self.enqueue()
        control = self.root / "automation" / "production_control.json"
        control.write_text(json.dumps({"schema_version": 1, "dispatch_mode": "hold"}), encoding="utf-8")
        writes_before = self.store.writes
        with patch("task_scheduler.recover_remote", side_effect=AssertionError("recovery must not run under HOLD")), \
             patch("task_scheduler.verify_pending_remote", side_effect=AssertionError("verification must not run under HOLD")):
            report = run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="scheduler-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.assertEqual(report["dispatch_mode"], "hold")
        self.assertEqual(report["processed_count"], 0)
        self.assertEqual(report["recovered_count"], 0)
        self.assertEqual(report["initial_verification"]["held"], True)
        self.assertEqual(self.store.writes, writes_before)
        self.assertEqual(self.store.document["tasks"][0]["status"], "QUEUED")

    def test_missing_or_invalid_production_control_fails_closed(self):
        control = self.root / "automation" / "production_control.json"
        control.unlink()
        from task_scheduler import production_dispatch_mode
        self.assertEqual(production_dispatch_mode(self.root), "hold")
        control.write_text("{invalid", encoding="utf-8")
        self.assertEqual(production_dispatch_mode(self.root), "hold")

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
            "Path('modules/uu.conf').write_text('changed', encoding='utf-8')\n"
            "print(json.dumps({'ok': True, 'value': 7, 'token_visible': False}))\n",
            encoding="utf-8",
        )
        self.enqueue()
        with self.assertRaisesRegex(RuntimeError, "scheduler stopped fail-closed"):
            run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="scheduler-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.assertNotEqual((self.root / "modules" / "uu.conf").read_text(encoding="utf-8"), "[General]\n")

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



    def test_hold_preserves_expired_lease_pending_failed_and_manual_authorization_states(self):
        self.enqueue()
        base = self.store.document["tasks"][0]
        expired = copy.deepcopy(base)
        expired.update({
            "task_id": "task_" + "1" * 24,
            "idempotency_key": "expired-task",
            "status": "CLAIMED",
            "attempts": 1,
            "lease": {"owner": "stale-worker", "token": "stale-token",
                      "expires_at": (self.now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")},
            "state_history": ["QUEUED", "CLAIMED"],
        })
        pending = copy.deepcopy(base)
        pending.update({
            "task_id": "task_" + "2" * 24,
            "idempotency_key": "pending-dispatch",
            "status": "VERIFYING",
            "attempts": 1,
            "lease": None,
            "result": {"dispatch_status": "PENDING", "workflow_run_id": 41840000001},
            "state_history": ["QUEUED", "CLAIMED", "VERIFYING"],
        })
        failed = copy.deepcopy(base)
        failed.update({
            "task_id": "task_" + "3" * 24,
            "idempotency_key": "failed-workflow",
            "status": "VERIFYING",
            "attempts": 1,
            "lease": None,
            "result": {"dispatch_status": "COMPLETED", "workflow_conclusion": "failure",
                       "workflow_run_id": 41840000002},
            "state_history": ["QUEUED", "CLAIMED", "VERIFYING"],
        })

        self.registry["programs"].extend([
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {"id": "workflow_auto_sync", "capabilities": ["deterministic_audit"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 1, "timeout_seconds": 300}},
        ])
        manual_idem = "production:manual-authorized:fp:41840000003"
        manual = {
            "task_id": "task_" + "4" * 24,
            "idempotency_key": manual_idem,
            "trace_id": "manual-hold-test",
            "requester_program_id": "workflow_automation_watchdog",
            "target_program_id": "workflow_auto_sync",
            "capability": "deterministic_audit",
            "created_at": stamp(self.now), "not_before": stamp(self.now),
            "priority": 100, "status": "QUEUED", "attempts": 0,
            "max_attempts": 1,
            "input": {
                "production_decision": "USER_AUTHORIZED_MANUAL_AUDIT",
                "production_fingerprint": "fp",
                "authorization_run_id": "41840000003",
                "authorization_run_attempt": "1",
                "authorization_actor": "maintainer",
                "authorization_actor_id": "678",
                "authorization_repository": "instarrys-bit/default",
                "authorization_workflow_ref": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
                "authorization_event": "workflow_dispatch",
                "authorization_ref": "refs/heads/main",
                "authorization_head_sha": "a" * 40,
                "authorization_requested": True,
                "authorization_target_program_id": "workflow_auto_sync",
                "authorization_idempotency_key": manual_idem,
                "baseline_source_event": "workflow_dispatch",
                "baseline_source_sha": "a" * 40,
            },
            "lease": None, "result": None, "last_error": None,
            "state_history": ["QUEUED"],
        }
        trusted_context = {
            "repository": "instarrys-bit/default",
            "workflow_ref": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "event": "workflow_dispatch", "actor": "maintainer", "actor_id": "678",
            "run_id": "41840000003", "run_attempt": "1", "ref": "refs/heads/main",
            "sha": "a" * 40, "manual_audit_requested": "true",
        }
        authorization = validate_manual_authorization(manual, trusted_context)
        manual_record = manual_authorization_record(manual, authorization, stamp(self.now))

        self.store.document["tasks"] = [expired, pending, failed, manual]
        self.store.document["manual_authorizations"] = {"41840000003": manual_record}
        before = json.loads(json.dumps(self.store.document))
        writes_before = self.store.writes
        control = self.root / "automation" / "production_control.json"
        control.write_text(json.dumps({"schema_version": 1, "dispatch_mode": "hold"}), encoding="utf-8")

        with patch("task_scheduler.recover_remote", side_effect=AssertionError("expired lease recovery must not run under HOLD")), \
             patch("task_scheduler.verify_pending_remote", side_effect=AssertionError("pending/failed dispatch verification must not run under HOLD")), \
             patch("task_scheduler.claim_remote", side_effect=AssertionError("manual or ordinary tasks must not be claimed under HOLD")):
            report = run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="scheduler-hold-matrix", max_tasks=10, root=self.root, now=self.now,
            )

        self.assertEqual(report["dispatch_mode"], "hold")
        self.assertEqual(report["processed_count"], 0)
        self.assertEqual(self.store.writes, writes_before)
        self.assertEqual(self.store.document, before)


    def test_read_only_plan_under_hold_reports_no_eligible_tasks_without_mutation(self):
        self.enqueue()
        control = self.root / "automation" / "production_control.json"
        control.write_text(json.dumps({"schema_version": 1, "dispatch_mode": "hold"}), encoding="utf-8")
        before = json.loads(json.dumps(self.store.document))
        writes_before = self.store.writes

        plan = build_execution_plan(
            self.store.document, self.registry, self.adapters, self.root, self.now
        )

        self.assertEqual(plan["dispatch_mode"], "hold")
        self.assertTrue(plan["read_only"])
        self.assertEqual(plan["eligible_task_ids"], [])
        self.assertEqual(len(plan["blocked"]), 1)
        self.assertIn("read-only planning only", plan["blocked"][0]["reason"])
        self.assertEqual(self.store.writes, writes_before)
        self.assertEqual(self.store.document, before)

    def test_scheduler_rejects_stale_or_missing_production_fingerprint_before_claim(self):
        manifest = {
            "schema_version": 1,
            "production_input_paths": ["modules/uu.conf"],
            "non_production_path_patterns": [],
        }
        (self.root / "automation" / "production_inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
        from production_intent import load_manifest, compute_fingerprint
        current = compute_fingerprint(self.root, load_manifest(self.root / "automation" / "production_inputs.json"))
        task = {"input": {"production_decision": "INPUT_CHANGED", "production_fingerprint": current}}
        self.assertEqual(assert_current_production_input(task, self.root), current)
        stale = {"input": {"production_decision": "INPUT_CHANGED", "production_fingerprint": "a" * 64}}
        with self.assertRaisesRegex(ValueError, "fingerprint is stale"):
            assert_current_production_input(stale, self.root)
        missing = {"input": {"production_decision": "INPUT_CHANGED"}}
        with self.assertRaisesRegex(ValueError, "missing a valid"):
            assert_current_production_input(missing, self.root)

    def test_new_production_enqueue_cancels_only_stale_unclaimed_automatic_tasks(self):
        registry = {"programs": [
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {"id": "workflow_auto_sync", "capabilities": ["deterministic_audit"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 2, "timeout_seconds": 300}},
        ]}
        store = MemoryStore()
        old = enqueue_auto_sync_task(
            store, registry, idempotency_key="production:input:" + "a" * 64 + ":old",
            input_payload={"production_fingerprint": "a" * 64, "production_decision": "INPUT_CHANGED", "production_reason": "old input"},
        )
        current = "b" * 64
        new = enqueue_auto_sync_task(
            store, registry, idempotency_key="production:input:" + current + ":new",
            input_payload={"production_fingerprint": current, "production_decision": "INPUT_CHANGED", "production_reason": "current input"},
        )
        tasks = {item["task_id"]: item for item in store.document["tasks"]}
        self.assertEqual(tasks[old["task_id"]]["status"], "CANCELLED")
        self.assertEqual(tasks[old["task_id"]]["state_history"], ["QUEUED", "CANCELLED"])
        self.assertEqual(tasks[old["task_id"]]["last_error"]["type"], "stale_production_input_superseded")
        self.assertEqual(tasks[new["task_id"]]["status"], "QUEUED")
        self.assertEqual(tasks[new["task_id"]]["input"]["production_fingerprint"], current)

    def test_same_fingerprint_queue_item_is_idempotent_and_not_superseded(self):
        registry = {"programs": [
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {"id": "workflow_auto_sync", "capabilities": ["deterministic_audit"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 2, "timeout_seconds": 300}},
        ]}
        store = MemoryStore()
        fingerprint = "c" * 64
        first = enqueue_auto_sync_task(
            store, registry, idempotency_key="production:input:" + fingerprint + ":same",
            input_payload={"production_fingerprint": fingerprint, "production_decision": "INPUT_CHANGED", "production_reason": "same input"},
        )
        replay = enqueue_auto_sync_task(
            store, registry, idempotency_key="production:input:" + fingerprint + ":same",
            input_payload={"production_fingerprint": fingerprint, "production_decision": "INPUT_CHANGED", "production_reason": "same input"},
        )
        self.assertFalse(replay["created"])
        self.assertEqual(first["task_id"], replay["task_id"])
        self.assertEqual(store.document["tasks"][0]["status"], "QUEUED")

    def test_scheduler_cancels_stale_queued_task_even_when_no_replacement_is_enqueued(self):
        manifest = {
            "schema_version": 1,
            "production_input_paths": ["modules/uu.conf"],
            "non_production_path_patterns": [],
        }
        (self.root / "automation" / "production_inputs.json").write_text(json.dumps(manifest), encoding="utf-8")
        registry = {"programs": [
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {"id": "workflow_auto_sync", "capabilities": ["deterministic_audit"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 2, "timeout_seconds": 300}},
        ]}
        store = MemoryStore()
        stale = enqueue_auto_sync_task(
            store, registry, idempotency_key="production:input:" + "d" * 64 + ":old",
            input_payload={"production_fingerprint": "d" * 64, "production_decision": "INPUT_CHANGED", "production_reason": "old input"},
        )
        superseded = supersede_stale_queued_production_tasks(store, registry, self.root)
        self.assertEqual(superseded, [stale["task_id"]])
        self.assertEqual(store.document["tasks"][0]["status"], "CANCELLED")
        self.assertEqual(store.document["tasks"][0]["last_error"]["type"], "stale_production_input_superseded")


    def test_explicit_resource_contract_allows_control_plane_paths_without_global_rulesets_only_cap(self):
        validate_repository_write_scope(
            ["automation/production_control.json", "rulesets/direct.list"],
            ["rulesets/direct.list"],
            ["automation/production_control.json", "rulesets/direct.list", "logical/production-pipeline"],
        )

    def test_explicit_resource_contract_still_rejects_modules_javascript_and_undeclared_paths(self):
        keys = ["modules/uu.conf", "modules/AdBlock.sgmodule", "scripts/Clean_Pro.js", "automation/production_control.json"]
        for path in ("modules/uu.conf", "modules/AdBlock.sgmodule", "scripts/Clean_Pro.js"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "protected modules or JavaScript"):
                    validate_repository_write_scope([path], [path], keys)
        with self.assertRaisesRegex(ValueError, "not declared"):
            validate_repository_write_scope(
                ["automation/unlisted.json"], ["automation/unlisted.json"],
                ["automation/production_control.json"],
            )
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            validate_repository_write_scope(["../modules/uu.conf"], ["../modules/uu.conf"], ["../modules/uu.conf"])

    def test_queued_retry_is_ineligible_until_backoff_expires(self):
        task = self.enqueue()["task"]
        task["attempts"] = 1
        task["last_error"] = {"type": "workflow_run_failed", "message": "first attempt failed"}
        task["state_history"] = ["QUEUED", "CLAIMED", "FAILED", "QUEUED"]
        task["not_before"] = stamp(self.now + timedelta(seconds=30))

        before_backoff = build_execution_plan(
            self.store.document, self.registry, self.adapters, self.root,
            self.now + timedelta(seconds=29),
        )
        after_backoff = build_execution_plan(
            self.store.document, self.registry, self.adapters, self.root,
            self.now + timedelta(seconds=31),
        )

        self.assertNotIn(task["task_id"], before_backoff["eligible_task_ids"])
        self.assertIn(task["task_id"], after_backoff["eligible_task_ids"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
