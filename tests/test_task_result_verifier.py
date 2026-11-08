import copy
import json
import hashlib
import sys
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import claim_remote, complete_remote, enqueue_remote, validate_candidate
from task_result_verifier import validate_json_schema, verify_pending_remote


class MemoryStore:
    def __init__(self):
        self.document = {"schema_version": 1, "revision": 0, "tasks": []}
        self.writes = 0

    def mutate(self, mutator, max_conflicts=5):
        candidate, result = mutator(copy.deepcopy(self.document))
        if candidate != self.document:
            self.document = candidate
            self.writes += 1
        return result

    def read(self):
        return type("Snapshot", (), {"document": copy.deepcopy(self.document), "content_sha": "fake-sha"})()


class TaskResultVerifierTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.registry = {"programs": [
            {"id": "script_requester", "capabilities": ["request"]},
            {"id": "script_target", "capabilities": ["test_capability"],
             "orchestration": {"enabled": True, "allowed_callers": ["script_requester"],
                               "max_attempts": 2, "timeout_seconds": 120}},
            {"id": "script_task_result_verifier", "capabilities": ["task_result_verification"],
             "orchestration": {"enabled": False, "allowed_callers": [],
                               "max_attempts": 0, "timeout_seconds": 300}},
            {"id": "script_assess_sources", "capabilities": ["source_assessment"],
             "orchestration": {"enabled": True, "allowed_callers": ["script_requester"],
                               "max_attempts": 2, "timeout_seconds": 240}},
            {"id": "workflow_auto_sync", "capabilities": ["production_sync"],
             "orchestration": {"enabled": True, "allowed_callers": ["script_requester"],
                               "max_attempts": 2, "timeout_seconds": 18000}},
        ]}
        self.now = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)
        self.schema = {
            "type": "object",
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
            "additionalProperties": False,
        }
        self.adapters = {"schema_version": 1, "adapters": [
            {
                "target_program_id": "script_target",
                "adapter_type": "python_cli",
                "enabled": True,
                "interface_status": "reviewed",
                "output_contract": self.schema,
            },
            {
                "target_program_id": "script_assess_sources",
                "adapter_type": "python_cli",
                "enabled": True,
                "interface_status": "reviewed",
                "output_contract": self.schema,
            },
        ]}

    def make_verifying_task(self, result):
        task = {"idempotency_key": "verifier:test:once",
                "requester_program_id": "script_requester",
                "target_program_id": "script_target",
                "capability": "test_capability", "input": {}}
        enqueue_remote(task, self.store, self.registry, self.now)
        eligible = {item["task_id"] for item in self.store.document["tasks"]}
        claimed = claim_remote("worker-a", self.store, self.registry,
                               eligible_task_ids=eligible, now=self.now)
        return complete_remote(
            claimed["task_id"], "worker-a", claimed["lease"]["token"],
            success=True, result=result, store=self.store,
            registry=self.registry, now=self.now,
        )

    def test_valid_result_is_accepted_only_by_independent_verifier(self):
        task = self.make_verifying_task({"ok": True})
        self.assertEqual(task["status"], "VERIFYING")
        report = verify_pending_remote(self.store, self.registry, self.adapters, self.now)
        self.assertEqual(report["verified"], [task["task_id"]])
        saved = self.store.document["tasks"][0]
        self.assertEqual(saved["status"], "SUCCEEDED")
        self.assertEqual(saved["verification"]["status"], "passed")
        self.assertEqual(saved["verification"]["verifier_program_id"], "script_task_result_verifier")

    def make_assessment_verifying_task(self, result):
        task = {"idempotency_key": "assessment-checkpoint:test:once",
                "requester_program_id": "script_requester",
                "target_program_id": "script_assess_sources",
                "capability": "source_assessment", "input": {}}
        enqueue_remote(task, self.store, self.registry, self.now)
        eligible = {item["task_id"] for item in self.store.document["tasks"]}
        claimed = claim_remote("worker-a", self.store, self.registry,
                               eligible_task_ids=eligible, now=self.now)
        verifying = complete_remote(
            claimed["task_id"], "worker-a", claimed["lease"]["token"],
            success=True, result=result, store=self.store,
            registry=self.registry, now=self.now,
        )
        checkpoint_url = "https://raw.githubusercontent.com/example/repo/main/list.txt"
        checkpoint_result = {"url": checkpoint_url}
        checkpoint_digest = hashlib.sha256(json.dumps(
            checkpoint_result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        self.store.document["tasks"][0]["assessment_checkpoint"] = {
            "schema_version": 1, "batch_id": "discovery-run:123:abcdef123456",
            "predecessor_artifact_sha256": "b" * 64,
            "completed": {checkpoint_url: {
                "result": checkpoint_result,
                "result_sha256": checkpoint_digest,
            }},
            "last_successful_url": checkpoint_url,
            "updated_at": "2026-11-05T00:00:00Z",
        }
        return verifying

    def test_assessment_checkpoint_is_cleared_only_after_successful_verification(self):
        task = self.make_assessment_verifying_task({"ok": True})
        report = verify_pending_remote(self.store, self.registry, self.adapters, self.now)
        self.assertEqual(report["verified"], [task["task_id"]])
        saved = self.store.document["tasks"][0]
        self.assertNotIn("assessment_checkpoint", saved)
        self.assertEqual(saved["assessment_checkpoint_summary"]["completed_url_count"], 1)

    def test_assessment_checkpoint_survives_failed_verification_for_retry(self):
        task = self.make_assessment_verifying_task({"ok": "wrong"})
        report = verify_pending_remote(self.store, self.registry, self.adapters, self.now)
        self.assertEqual(report["rejected"], [task["task_id"]])
        saved = self.store.document["tasks"][0]
        self.assertIn("assessment_checkpoint", saved)
        self.assertEqual(saved["status"], "QUEUED")

    def test_invalid_result_is_retried_and_not_marked_successful(self):
        task = self.make_verifying_task({"ok": "not-a-boolean"})
        report = verify_pending_remote(self.store, self.registry, self.adapters, self.now)
        self.assertEqual(report["rejected"], [task["task_id"]])
        saved = self.store.document["tasks"][0]
        self.assertEqual(saved["status"], "QUEUED")
        self.assertEqual(saved["verification"]["status"], "failed")
        self.assertEqual(saved["last_error"]["type"], "result_verification_failed")

    def test_github_backed_task_cannot_be_marked_succeeded_without_verification(self):
        self.make_verifying_task({"ok": True})
        candidate = copy.deepcopy(self.store.document)
        task = candidate["tasks"][0]
        task["status"] = "SUCCEEDED"
        task["state_history"].append("SUCCEEDED")
        with self.assertRaisesRegex(ValueError, "requires independent verification"):
            validate_candidate(candidate, self.registry)

    def test_missing_reviewed_contract_blocks_without_mutation(self):
        task = self.make_verifying_task({"ok": True})
        before = copy.deepcopy(self.store.document)
        report = verify_pending_remote(self.store, self.registry, {"schema_version": 1, "adapters": []}, self.now)
        self.assertEqual(report["verified"], [])
        self.assertEqual(report["rejected"], [])
        self.assertEqual(report["blocked"][0]["task_id"], task["task_id"])
        self.assertEqual(self.store.document, before)

    def test_cancelled_watchdog_claim_without_child_run_is_dead_lettered_and_releases_claim(self):
        enqueue_remote({
            "idempotency_key": "watchdog-abandoned-claim:test",
            "requester_program_id": "script_requester",
            "target_program_id": "workflow_auto_sync",
            "capability": "production_sync",
            "input": {},
        }, self.store, self.registry, self.now)
        task_id = self.store.document["tasks"][0]["task_id"]
        claim_remote("12345", self.store, self.registry, eligible_task_ids={task_id}, now=self.now)
        task = self.store.document["tasks"][0]
        task["dispatch_intent"] = {
            "workflow_id": 99, "workflow_path": ".github/workflows/auto_sync.yml",
            "ref": "main", "requested_head_sha": "a" * 40, "task_id": task_id,
            "dispatch_attempt": 1, "correlation_id": f"{task_id}-a1",
            "correlation_title": f"Automation task {task_id}-a1",
            "inputs": {"automation_task_id": f"{task_id}-a1"},
            "prepared_at": "2026-11-03T03:50:00Z",
        }
        adapters = {"schema_version": 1, "adapters": [{
            "target_program_id": "workflow_auto_sync",
            "adapter_type": "github_actions_workflow", "enabled": True,
            "interface_status": "workflow_dispatch_reviewed",
            "workflow": {"path": ".github/workflows/auto_sync.yml", "dispatchable": True},
        }]}
        client = Mock()
        client.get_run.return_value = {
            "status": "completed", "conclusion": "cancelled", "head_branch": "main",
            "path": ".github/workflows/automation-watchdog.yml",
            "updated_at": "2026-11-03T03:57:00Z",
        }
        with patch("task_result_verifier.inspect_correlated_run", return_value={
            "state": "pending", "reason": "correlated workflow run is not visible yet",
        }):
            report = verify_pending_remote(self.store, self.registry, adapters, self.now, workflow_client=client)
        saved = self.store.document["tasks"][0]
        self.assertEqual(report["rejected"], [task_id])
        self.assertEqual(saved["status"], "DEAD_LETTER")
        self.assertIsNone(saved["lease"])
        self.assertEqual(saved["verification"]["status"], "failed")
        self.assertEqual(saved["last_error"]["type"], "abandoned_scheduler_run_dispatch_outcome_unknown")
        client.get_run.assert_called_once_with(12345)

    def test_failed_correlated_workflow_clears_claim_lease_before_requeue(self):
        enqueue_remote({
            "idempotency_key": "workflow-failure-lease:test",
            "requester_program_id": "script_requester",
            "target_program_id": "workflow_auto_sync",
            "capability": "production_sync",
            "input": {},
        }, self.store, self.registry, self.now)
        task_id = self.store.document["tasks"][0]["task_id"]
        claim_remote("12345", self.store, self.registry, eligible_task_ids={task_id}, now=self.now)
        self.store.document["tasks"][0]["dispatch_intent"] = {
            "workflow_id": 99, "workflow_path": ".github/workflows/auto_sync.yml",
            "ref": "main", "requested_head_sha": "a" * 40, "task_id": task_id,
            "dispatch_attempt": 1, "correlation_id": f"{task_id}-a1",
            "correlation_title": f"Automation task {task_id}-a1",
            "inputs": {"automation_task_id": f"{task_id}-a1"},
            "prepared_at": "2026-11-03T03:50:00Z",
        }
        adapters = {"schema_version": 1, "adapters": [{
            "target_program_id": "workflow_auto_sync",
            "adapter_type": "github_actions_workflow", "enabled": True,
            "interface_status": "workflow_dispatch_reviewed",
            "workflow": {"path": ".github/workflows/auto_sync.yml", "dispatchable": True},
        }]}
        evidence = {
            "run_id": 987, "status": "completed", "conclusion": "cancelled",
            "head_sha": "a" * 40, "requested_head_sha": "a" * 40,
            "head_sha_relationship": "exact", "html_url": "https://example.invalid/run/987",
        }
        with patch("task_result_verifier.inspect_correlated_run", return_value={
            "state": "failure", "evidence": evidence, "reason": "workflow cancelled",
        }):
            report = verify_pending_remote(self.store, self.registry, adapters, self.now, workflow_client=Mock())
        saved = self.store.document["tasks"][0]
        self.assertEqual(report["rejected"], [task_id])
        self.assertEqual(saved["status"], "QUEUED")
        self.assertIsNone(saved["lease"])
        self.assertNotIn("dispatch_intent", saved)

    def test_schema_rejects_unsupported_keywords(self):
        with self.assertRaisesRegex(ValueError, "unsupported schema keywords"):
            validate_json_schema({"ok": True}, {"type": "object", "patternProperties": {}})

    def test_schema_checks_nested_arrays_and_additional_properties(self):
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {"type": "array", "minItems": 1,
                          "items": {"type": "integer", "minimum": 1}}
            },
            "additionalProperties": False,
        }
        self.assertEqual(validate_json_schema({"items": [1, 2]}, schema), [])
        self.assertTrue(validate_json_schema({"items": [0], "extra": True}, schema))


if __name__ == "__main__":
    unittest.main(verbosity=2)
