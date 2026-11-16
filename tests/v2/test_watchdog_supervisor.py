import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))
from watchdog_supervisor import plan_recovery
from runtime import empty_state, append_event


class WatchdogSupervisorTests(unittest.TestCase):
    def make_task(self, *, task_expiry, resource_expiry=None, max_attempts=3):
        state = empty_state("watchdog-test")
        state, _ = append_event(state, event_type="TASK_ENQUEUED",
            payload={"task_id":"task_watchdog","max_attempts":max_attempts},
            actor="watchdog", idempotency_key="enq", expected_revision=0,
            created_at="2026-11-17T00:00:00Z")
        state, _ = append_event(state, event_type="TASK_CLAIMED",
            payload={"task_id":"task_watchdog","lease_id":"task-lease-1","owner":"worker","token":"secret-task-token","expires_at":task_expiry},
            actor="watchdog", idempotency_key="claim", expected_revision=1,
            created_at="2026-11-17T00:01:00Z")
        if resource_expiry:
            state, _ = append_event(state, event_type="RESOURCE_ACQUIRED",
                payload={"resource_key":"rulesets/direct.list","lease_id":"resource-lease-1","task_id":"task_watchdog","owner":"worker","fencing_token":1,"expires_at":resource_expiry},
                actor="storage_management", idempotency_key="resource", expected_revision=2,
                created_at="2026-11-17T00:02:00Z")
        return state

    def test_uninitialized_state_is_noop_and_never_dispatches(self):
        plan = plan_recovery(None, observed_at="2026-11-17T00:20:00Z")
        self.assertEqual(plan["status"], "NOT_INITIALIZED")
        self.assertEqual(plan["actions"], [])
        self.assertFalse(plan["dispatch_enabled"])

    def test_expired_resources_then_task_then_requeue_are_ordered(self):
        state = self.make_task(task_expiry="2026-11-17T00:10:00Z",
                               resource_expiry="2026-11-17T00:08:00Z")
        plan = plan_recovery(state, observed_at="2026-11-17T00:20:00Z")
        self.assertEqual([a["event_type"] for a in plan["actions"]], [
            "RESOURCE_LEASE_EXPIRED", "TASK_LEASE_EXPIRED", "TASK_REQUEUED"
        ])
        self.assertEqual([a["expected_revision"] for a in plan["actions"]], [3,4,5])
        self.assertNotIn("secret-task-token", json.dumps(plan))
        self.assertFalse(plan["dispatch_enabled"])

    def test_live_resource_blocks_task_requeue(self):
        state = self.make_task(task_expiry="2026-11-17T00:10:00Z",
                               resource_expiry="2026-11-17T00:30:00Z")
        plan = plan_recovery(state, observed_at="2026-11-17T00:20:00Z")
        self.assertEqual([a["event_type"] for a in plan["actions"]], ["TASK_LEASE_EXPIRED"])

    def test_unexpired_task_lease_produces_no_recovery_action(self):
        state = self.make_task(task_expiry="2026-11-17T00:30:00Z")
        plan = plan_recovery(state, observed_at="2026-11-17T00:20:00Z")
        self.assertEqual(plan["actions"], [])
        self.assertEqual(plan["status"], "NO_ACTIONS")

    def test_exhausted_retry_budget_dead_letters_instead_of_requeue(self):
        state = self.make_task(task_expiry="2026-11-17T00:10:00Z", max_attempts=1)
        plan = plan_recovery(state, observed_at="2026-11-17T00:20:00Z")
        self.assertEqual([a["event_type"] for a in plan["actions"]], [
            "TASK_LEASE_EXPIRED", "TASK_DEAD_LETTER"
        ])

    def test_already_expired_task_with_released_resources_can_requeue(self):
        state = self.make_task(task_expiry="2026-11-17T00:10:00Z")
        state, _ = append_event(state, event_type="TASK_LEASE_EXPIRED",
            payload={"task_id":"task_watchdog","lease_id":"task-lease-1","owner":"worker","token":"secret-task-token"},
            actor="storage_management", idempotency_key="expired", expected_revision=2,
            created_at="2026-11-17T00:11:00Z")
        plan = plan_recovery(state, observed_at="2026-11-17T00:20:00Z")
        self.assertEqual([a["event_type"] for a in plan["actions"]], ["TASK_REQUEUED"])
        self.assertNotIn("secret-task-token", json.dumps(plan))


if __name__ == "__main__":
    unittest.main()
