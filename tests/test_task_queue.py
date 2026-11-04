import hashlib
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

    def assessment_task(self, **overrides):
        root, queue, registry = self.make_store()
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["programs"][1].update({
            "id": "script_assess_sources",
            "capabilities": ["source_assessment"],
            "orchestration": {
                "enabled": True, "allowed_callers": ["script_requester"],
                "max_attempts": 2, "timeout_seconds": 240,
            },
        })
        registry.write_text(json.dumps(data), encoding="utf-8")
        result = {
            "url": "https://raw.githubusercontent.com/example/repo/main/list.txt",
            "parser_candidate": "domain-only",
            "domain_fingerprints": ["a" * 32],
        }
        digest = hashlib.sha256(json.dumps(
            result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        checkpoint = {
            "schema_version": 1,
            "batch_id": "discovery-run:123456:abcdef123456",
            "predecessor_artifact_sha256": "b" * 64,
            "completed": {result["url"]: {"result": result, "result_sha256": digest}},
            "last_successful_url": result["url"],
            "updated_at": "2026-11-05T00:00:00Z",
        }
        task = self.task(
            target_program_id="script_assess_sources",
            capability="source_assessment",
            assessment_checkpoint=checkpoint,
            **overrides,
        )
        return root, queue, registry, task

    def test_valid_bounded_assessment_checkpoint_is_accepted(self):
        root, queue, registry, task = self.assessment_task()
        self.write_task(queue, task)
        self.assertEqual(self.validate(root, queue, registry)["task_count"], 1)

    def test_assessment_checkpoint_rejects_digest_mismatch(self):
        root, queue, registry, task = self.assessment_task()
        task["assessment_checkpoint"]["completed"][
            "https://raw.githubusercontent.com/example/repo/main/list.txt"
        ]["result_sha256"] = "0" * 64
        self.write_task(queue, task)
        with self.assertRaisesRegex(ValueError, "result digest mismatch"):
            self.validate(root, queue, registry)

    def test_assessment_checkpoint_is_rejected_for_non_assessment_task(self):
        root, queue, registry, task = self.assessment_task()
        task["target_program_id"] = "script_target"
        task["capability"] = "test_capability"
        self.write_task(queue, task)
        with self.assertRaisesRegex(ValueError, "not allowed"):
            self.validate(root, queue, registry)

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

    def test_terminal_history_remains_valid_when_target_is_disabled(self):
        root, queue, registry = self.make_store()
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["programs"][1]["orchestration"]["enabled"] = False
        data["programs"][1]["orchestration"]["allowed_callers"] = []
        data["programs"][1]["orchestration"]["max_attempts"] = 0
        registry.write_text(json.dumps(data), encoding="utf-8")
        terminal = self.task(
            status="DEAD_LETTER",
            attempts=1,
            max_attempts=1,
            state_history=["QUEUED", "CLAIMED", "DEAD_LETTER"],
            last_error={"type": "bounded_canary_failed", "message": "publisher cache filter"},
        )
        self.write_task(queue, terminal)
        self.assertEqual(self.validate(root, queue, registry)["task_count"], 1)

    def test_exhausted_failed_history_remains_valid_when_target_is_disabled(self):
        root, queue, registry = self.make_store()
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["programs"][1]["orchestration"]["enabled"] = False
        data["programs"][1]["orchestration"]["allowed_callers"] = []
        data["programs"][1]["orchestration"]["max_attempts"] = 0
        registry.write_text(json.dumps(data), encoding="utf-8")
        terminal = self.task(
            status="FAILED",
            attempts=1,
            max_attempts=1,
            state_history=["QUEUED", "CLAIMED", "FAILED"],
            last_error={"type": "bounded_canary_failed", "message": "publisher cache filter"},
        )
        self.write_task(queue, terminal)
        self.assertEqual(self.validate(root, queue, registry)["task_count"], 1)

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
