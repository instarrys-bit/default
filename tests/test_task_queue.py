import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from task_queue import validate_task_queue


class TaskQueueTests(unittest.TestCase):
    def make_store(self):
        root = Path(tempfile.mkdtemp())
        (root / "automation").mkdir()
        target = {
            "id": "script_target",
            "capabilities": ["test_capability"],
            "orchestration": {
                "enabled": True,
                "allowed_callers": ["script_requester"],
                "max_attempts": 2,
                "timeout_seconds": 120,
            },
        }
        requester = {"id": "script_requester", "capabilities": ["request"]}
        registry = root / "automation" / "program_registry.json"
        registry.write_text(json.dumps({"programs": [requester, target]}), encoding="utf-8")
        queue = root / "automation" / "task_queue.json"
        queue.write_text(json.dumps({"schema_version": 1, "revision": 0, "tasks": []}), encoding="utf-8")
        return root, queue, registry

    def task(self, **overrides):
        value = {
            "task_id": "task_0123456789abcdef01234567",
            "idempotency_key": "test:once",
            "trace_id": "trace-001",
            "requester_program_id": "script_requester",
            "target_program_id": "script_target",
            "capability": "test_capability",
            "created_at": "2026-11-03T00:00:00Z",
            "not_before": "2026-11-03T00:00:00+00:00",
            "priority": 50,
            "status": "QUEUED",
            "attempts": 0,
            "max_attempts": 2,
            "input": {},
            "lease": None,
            "result": None,
            "last_error": None,
            "state_history": ["QUEUED"],
        }
        value.update(overrides)
        return value

    def write_task(self, queue, *tasks):
        queue.write_text(json.dumps({"schema_version": 1, "revision": 1, "tasks": list(tasks)}), encoding="utf-8")

    def validate(self, root, queue, registry):
        return validate_task_queue(root, queue, registry)

    def test_empty_queue_is_valid(self):
        root, queue, registry = self.make_store()
        self.assertEqual(self.validate(root, queue, registry)["task_count"], 0)

    def test_valid_queued_task_is_accepted(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task())
        self.assertEqual(self.validate(root, queue, registry)["task_count"], 1)

    def test_rejects_duplicate_idempotency_key(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task(), self.task(task_id="task_1123456789abcdef01234567"))
        with self.assertRaisesRegex(ValueError, "duplicate idempotency_key"):
            self.validate(root, queue, registry)

    def test_rejects_disabled_target(self):
        root, queue, registry = self.make_store()
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["programs"][1]["orchestration"]["enabled"] = False
        data["programs"][1]["orchestration"]["allowed_callers"] = []
        registry.write_text(json.dumps(data), encoding="utf-8")
        self.write_task(queue, self.task())
        with self.assertRaisesRegex(ValueError, "not enabled"):
            self.validate(root, queue, registry)

    def test_rejects_unauthorized_requester(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task(requester_program_id="script_unknown"))
        with self.assertRaisesRegex(ValueError, "unknown requester"):
            self.validate(root, queue, registry)

    def test_rejects_unregistered_capability(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task(capability="unregistered"))
        with self.assertRaisesRegex(ValueError, "capability not declared"):
            self.validate(root, queue, registry)

    def test_claimed_task_requires_lease(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task(status="CLAIMED", state_history=["QUEUED", "CLAIMED"]))
        with self.assertRaisesRegex(ValueError, "requires a lease owner"):
            self.validate(root, queue, registry)

    def test_rejects_timezone_free_timestamps(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task(created_at="2026-11-03T00:00:00"))
        with self.assertRaisesRegex(ValueError, "must include a timezone"):
            self.validate(root, queue, registry)

    def test_rejects_retry_budget_above_target_policy(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task(max_attempts=3))
        with self.assertRaisesRegex(ValueError, "exceed the registered retry budget"):
            self.validate(root, queue, registry)

    def test_rejects_illegal_state_transition(self):
        root, queue, registry = self.make_store()
        self.write_task(queue, self.task(status="SUCCEEDED", state_history=["QUEUED", "SUCCEEDED"], result={"ok": True}))
        with self.assertRaisesRegex(ValueError, "illegal transition"):
            self.validate(root, queue, registry)


if __name__ == "__main__":
    unittest.main()
