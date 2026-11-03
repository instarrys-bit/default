import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import (
    claim_remote, complete_remote, enqueue_remote, recover_remote,
)


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


class RemoteQueueRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.registry = {"programs": [
            {"id": "script_requester", "capabilities": ["request"]},
            {"id": "script_target", "capabilities": ["test_capability"],
             "orchestration": {"enabled": True, "allowed_callers": ["script_requester"],
                               "max_attempts": 2, "timeout_seconds": 120}},
        ]}
        self.now = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)

    def claim(self, worker_id, now):
        eligible = {task["task_id"] for task in self.store.document["tasks"]}
        return claim_remote(worker_id, self.store, self.registry,
                            eligible_task_ids=eligible, now=now)

    def payload(self, **overrides):
        value = {"idempotency_key": "remote:test:once", "requester_program_id": "script_requester",
                 "target_program_id": "script_target", "capability": "test_capability",
                 "priority": 50, "input": {"value": 1}}
        value.update(overrides)
        return value

    def test_enqueue_is_idempotent_and_rejects_payload_reuse(self):
        first = enqueue_remote(self.payload(), self.store, self.registry, self.now)
        second = enqueue_remote(self.payload(), self.store, self.registry, self.now)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["task"]["task_id"], second["task"]["task_id"])
        with self.assertRaisesRegex(ValueError, "different task payload"):
            enqueue_remote(self.payload(input={"value": 2}), self.store, self.registry, self.now)

    def test_claim_respects_priority_and_uses_lease(self):
        enqueue_remote(self.payload(idempotency_key="low", priority=10), self.store, self.registry, self.now)
        enqueue_remote(self.payload(idempotency_key="high", priority=90), self.store, self.registry, self.now)
        task = self.claim("worker-a", self.now)
        self.assertEqual(task["idempotency_key"], "high")
        self.assertEqual(task["status"], "CLAIMED")
        self.assertEqual(task["lease"]["owner"], "worker-a")

    def test_completion_requires_matching_lease(self):
        enqueue_remote(self.payload(), self.store, self.registry, self.now)
        task = claim_remote("worker-a", self.store, self.registry, self.now)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            complete_remote(task["task_id"], "worker-b", task["lease"]["token"],
                            success=True, result={"ok": True}, store=self.store,
                            registry=self.registry, now=self.now)
        done = complete_remote(task["task_id"], "worker-a", task["lease"]["token"],
                               success=True, result={"ok": True}, store=self.store,
                               registry=self.registry, now=self.now)
        self.assertEqual(done["status"], "VERIFYING")

    def test_failure_retries_then_dead_letters(self):
        enqueue_remote(self.payload(), self.store, self.registry, self.now)
        first = claim_remote("worker-a", self.store, self.registry, self.now)
        retry = complete_remote(first["task_id"], "worker-a", first["lease"]["token"],
                                success=False, error={"type": "temporary"}, store=self.store,
                                registry=self.registry, now=self.now)
        self.assertEqual(retry["status"], "QUEUED")
        later = self.now + timedelta(seconds=31)
        second = self.claim("worker-b", later)
        final = complete_remote(second["task_id"], "worker-b", second["lease"]["token"],
                                 success=False, error={"type": "failed"}, store=self.store,
                                 registry=self.registry, now=later)
        self.assertEqual(final["status"], "DEAD_LETTER")

    def test_expired_lease_is_recovered(self):
        enqueue_remote(self.payload(), self.store, self.registry, self.now)
        task = claim_remote("worker-a", self.store, self.registry, self.now)
        recovered = recover_remote(self.store, self.registry, self.now + timedelta(seconds=121))
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["task_id"], task["task_id"])
        self.assertEqual(recovered[0]["status"], "QUEUED")

    def test_empty_claim_and_recovery_do_not_write(self):
        self.assertIsNone(claim_remote("worker-a", self.store, self.registry, self.now))
        self.assertEqual(recover_remote(self.store, self.registry, self.now), [])
        self.assertEqual(self.store.writes, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
