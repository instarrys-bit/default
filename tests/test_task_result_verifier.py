import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import claim_remote, complete_remote, enqueue_remote
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
        ]}
        self.now = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)
        self.schema = {
            "type": "object",
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
            "additionalProperties": False,
        }
        self.adapters = {"schema_version": 1, "adapters": [{
            "target_program_id": "script_target",
            "enabled": True,
            "interface_status": "reviewed",
            "output_contract": self.schema,
        }]}

    def make_verifying_task(self, result):
        task = {"idempotency_key": "verifier:test:once",
                "requester_program_id": "script_requester",
                "target_program_id": "script_target",
                "capability": "test_capability", "input": {}}
        enqueue_remote(task, self.store, self.registry, self.now)
        claimed = claim_remote("worker-a", self.store, self.registry, self.now)
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

    def test_invalid_result_is_retried_and_not_marked_successful(self):
        task = self.make_verifying_task({"ok": "not-a-boolean"})
        report = verify_pending_remote(self.store, self.registry, self.adapters, self.now)
        self.assertEqual(report["rejected"], [task["task_id"]])
        saved = self.store.document["tasks"][0]
        self.assertEqual(saved["status"], "QUEUED")
        self.assertEqual(saved["verification"]["status"], "failed")
        self.assertEqual(saved["last_error"]["type"], "result_verification_failed")

    def test_missing_reviewed_contract_blocks_without_mutation(self):
        task = self.make_verifying_task({"ok": True})
        before = copy.deepcopy(self.store.document)
        report = verify_pending_remote(self.store, self.registry, {"schema_version": 1, "adapters": []}, self.now)
        self.assertEqual(report["verified"], [])
        self.assertEqual(report["rejected"], [])
        self.assertEqual(report["blocked"][0]["task_id"], task["task_id"])
        self.assertEqual(self.store.document, before)

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
