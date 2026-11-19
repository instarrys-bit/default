import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))
from runtime import (
    Conflict, append_event, apply_watchdog_recovery_plan,
    apply_watchdog_recovery_plan_to_backend, canonical_bytes, empty_state, project, sha256,
)
from watchdog_supervisor import plan_recovery


class MemoryStateBackend:
    def __init__(self, state, fail_on_write=None):
        self.state = copy.deepcopy(state)
        self.blob_sha = sha256(canonical_bytes(self.state))
        self.write_count = 0
        self.fail_on_write = fail_on_write

    def read(self):
        return copy.deepcopy(self.state), self.blob_sha

    def compare_and_swap(self, candidate, *, expected_revision, expected_blob_sha, message):
        if self.state["revision"] != expected_revision or self.blob_sha != expected_blob_sha:
            raise Conflict("storage state compare-and-swap failed")
        if candidate["revision"] != expected_revision + 1:
            raise ValueError("candidate revision must advance exactly once")
        self.write_count += 1
        if self.fail_on_write == self.write_count:
            raise Conflict("simulated CAS conflict")
        self.state = copy.deepcopy(candidate)
        self.blob_sha = sha256(canonical_bytes(self.state))
        return self.blob_sha


class StorageManagerRecoveryApplyTests(unittest.TestCase):
    def make_state(self):
        state = empty_state("apply-test")
        state, _ = append_event(state, event_type="TASK_ENQUEUED",
            payload={"task_id":"task_apply","max_attempts":3}, actor="watchdog",
            idempotency_key="enq", expected_revision=0, created_at="2026-11-17T00:00:00Z")
        state, _ = append_event(state, event_type="TASK_CLAIMED",
            payload={"task_id":"task_apply","lease_id":"task-lease","owner":"worker","token":"secret-task-token","expires_at":"2026-11-17T00:10:00Z"},
            actor="watchdog", idempotency_key="claim", expected_revision=1, created_at="2026-11-17T00:01:00Z")
        state, _ = append_event(state, event_type="RESOURCE_ACQUIRED",
            payload={"resource_key":"rulesets/direct.list","lease_id":"resource-lease","task_id":"task_apply","owner":"worker","fencing_token":1,"expires_at":"2026-11-17T00:08:00Z"},
            actor="storage_management", idempotency_key="resource", expected_revision=2, created_at="2026-11-17T00:02:00Z")
        return state

    def make_plan(self, state):
        return plan_recovery(state, observed_at="2026-11-17T00:20:00Z")

    def test_pure_apply_rehydrates_secret_and_applies_in_safe_order(self):
        state = self.make_state()
        plan = self.make_plan(state)
        self.assertNotIn("secret-task-token", json.dumps(plan))
        candidate, result = apply_watchdog_recovery_plan(state, plan, actor="storage_management")
        projection = project(candidate)
        self.assertEqual(candidate["revision"], 6)
        self.assertEqual(projection["tasks"]["task_apply"]["status"], "QUEUED")
        self.assertEqual(projection["tasks"]["task_apply"]["task_lease"]["status"], "RELEASED")
        self.assertEqual(projection["resource_leases"]["rulesets/direct.list"]["status"], "EXPIRED")
        self.assertEqual([x["event_type"] for x in result["applied_actions"]], [
            "RESOURCE_LEASE_EXPIRED", "TASK_LEASE_EXPIRED", "TASK_REQUEUED"
        ])
        self.assertNotIn("secret-task-token", json.dumps(result))
        self.assertIn("secret-task-token", json.dumps(candidate["events"]))

    def test_backend_apply_uses_one_verified_cas_per_event(self):
        backend = MemoryStateBackend(self.make_state())
        plan = self.make_plan(backend.state)
        result = apply_watchdog_recovery_plan_to_backend(backend, plan, actor="storage_management")
        self.assertEqual(result["applied_count"], 3)
        self.assertEqual(backend.write_count, 3)
        self.assertEqual(backend.state["revision"], 6)
        self.assertEqual(project(backend.state)["tasks"]["task_apply"]["status"], "QUEUED")

    def test_non_storage_manager_cannot_apply_watchdog_plan(self):
        state = self.make_state()
        with self.assertRaises(PermissionError):
            apply_watchdog_recovery_plan(state, self.make_plan(state), actor="watchdog_v2")

    def test_stale_plan_revision_is_rejected_before_any_change(self):
        state = self.make_state()
        plan = self.make_plan(state)
        newer, _ = append_event(state, event_type="TASK_LEASE_EXPIRED",
            payload={"task_id":"task_apply","lease_id":"task-lease","owner":"worker","token":"secret-task-token"},
            actor="storage_management", idempotency_key="already-expired", expected_revision=3,
            created_at="2026-11-17T00:11:00Z")
        with self.assertRaisesRegex(Conflict, "revision is stale"):
            apply_watchdog_recovery_plan(newer, plan, actor="storage_management")

    def test_plan_cannot_smuggle_opaque_task_lease_token(self):
        state = self.make_state()
        plan = self.make_plan(state)
        plan["actions"][1]["token"] = "secret-task-token"
        with self.assertRaisesRegex(PermissionError, "must never be included"):
            apply_watchdog_recovery_plan(state, plan, actor="storage_management")

    def test_changed_lease_identity_is_rejected(self):
        state = self.make_state()
        plan = self.make_plan(state)
        plan["actions"][1]["lease_id"] = "stale-lease"
        with self.assertRaisesRegex(Conflict, "lease changed"):
            apply_watchdog_recovery_plan(state, plan, actor="storage_management")

    def test_partial_cas_failure_stops_before_task_requeue(self):
        backend = MemoryStateBackend(self.make_state(), fail_on_write=2)
        plan = self.make_plan(backend.state)
        with self.assertRaisesRegex(Conflict, "simulated CAS conflict"):
            apply_watchdog_recovery_plan_to_backend(backend, plan, actor="storage_management")
        self.assertEqual(backend.state["revision"], 4)
        self.assertEqual(project(backend.state)["resource_leases"]["rulesets/direct.list"]["status"], "EXPIRED")
        self.assertEqual(project(backend.state)["tasks"]["task_apply"]["task_lease"]["status"], "ACTIVE")
        self.assertEqual(project(backend.state)["tasks"]["task_apply"]["status"], "CLAIMED")


if __name__ == "__main__":
    unittest.main()
