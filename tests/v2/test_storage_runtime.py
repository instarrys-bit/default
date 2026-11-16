import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from runtime import (
    Conflict, append_event, assert_automation_write_allowed, empty_state,
    project, validate_state,
)


class StorageV2Tests(unittest.TestCase):
    def setUp(self):
        self.state = empty_state("test-epoch")

    def append(self, kind, payload, key, revision=None):
        candidate, result = append_event(
            self.state, event_type=kind, payload=payload, actor="test",
            idempotency_key=key,
            expected_revision=self.state["revision"] if revision is None else revision,
            created_at="2026-11-17T00:00:00Z",
        )
        self.state = candidate
        return result

    def test_empty_epoch_and_projection(self):
        self.assertEqual(project(self.state)["revision"], 0)
        self.assertEqual(project(self.state)["task_count"], 0)

    def test_append_event_hash_chain_and_revision(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enqueue-1")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"lease-1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim-1")
        self.assertEqual(self.state["revision"], 2)
        self.assertEqual(project(self.state)["tasks"]["task-1"]["status"], "CLAIMED")
        validate_state(self.state)

    def test_rejects_stale_revision(self):
        with self.assertRaises(Conflict):
            append_event(self.state, event_type="TASK_ENQUEUED",
                         payload={"task_id":"task-1","max_attempts":2},
                         actor="test", idempotency_key="k", expected_revision=9)

    def test_idempotent_replay_returns_existing_event(self):
        first, result = append_event(self.state, event_type="TASK_ENQUEUED",
            payload={"task_id":"task-1","max_attempts":2}, actor="test",
            idempotency_key="same", expected_revision=0, created_at="2026-11-17T00:00:00Z")
        replay, replay_result = append_event(first, event_type="TASK_ENQUEUED",
            payload={"task_id":"task-1","max_attempts":2}, actor="test",
            idempotency_key="same", expected_revision=1, created_at="2026-11-17T00:00:00Z")
        self.assertFalse(replay_result["created"])
        self.assertEqual(replay["revision"], 1)

    def test_idempotency_key_cannot_be_reused_for_different_payload(self):
        first, _ = append_event(self.state, event_type="TASK_ENQUEUED",
            payload={"task_id":"task-1","max_attempts":2}, actor="test",
            idempotency_key="same", expected_revision=0, created_at="2026-11-17T00:00:00Z")
        with self.assertRaises(Conflict):
            append_event(first, event_type="TASK_ENQUEUED",
                payload={"task_id":"task-2","max_attempts":2}, actor="test",
                idempotency_key="same", expected_revision=1, created_at="2026-11-17T00:00:00Z")

    def test_tampered_event_is_detected(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "k")
        broken = copy.deepcopy(self.state)
        broken["events"][0]["payload"]["task_id"] = "tampered"
        with self.assertRaisesRegex(ValueError, "event hash mismatch"):
            validate_state(broken)

    def test_task_transition_must_be_valid(self):
        queued, _ = append_event(self.state, event_type="TASK_ENQUEUED",
            payload={"task_id":"task-1","max_attempts":2}, actor="test",
            idempotency_key="enqueue", expected_revision=0,
            created_at="2026-11-17T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "invalid task transition"):
            append_event(queued, event_type="TASK_SUCCEEDED",
                payload={"task_id":"task-1","result_artifact_id":"sha"}, actor="test",
                idempotency_key="k", expected_revision=1)

    def test_resource_fencing_tokens_increase(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enqueue")
        self.append("RESOURCE_ACQUIRED", {"resource_key":"rulesets/direct.list","lease_id":"l1","task_id":"task-1","owner":"worker","fencing_token":1,"expires_at":"2026-11-17T00:10:00Z"}, "resource-1")
        self.append("RESOURCE_RELEASED", {"resource_key":"rulesets/direct.list","lease_id":"l1","fencing_token":1}, "resource-2")
        self.append("RESOURCE_ACQUIRED", {"resource_key":"rulesets/direct.list","lease_id":"l2","task_id":"task-1","owner":"worker2","fencing_token":2,"expires_at":"2026-11-17T00:20:00Z"}, "resource-3")
        self.assertEqual(project(self.state)["resource_leases"]["rulesets/direct.list"]["fencing_token"], 2)

    def test_uu_conf_automation_only_read_only(self):
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed("modules/uu.conf", "production_worker")
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed("modules/AdBlock.sgmodule", "watchdog")
        self.assertIsNone(assert_automation_write_allowed("modules/uu.conf", "human_user"))

    def test_automation_default_deny(self):
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed("README.md", "production_worker")
        self.assertIsNone(assert_automation_write_allowed("rulesets/direct.list", "storage_management"))


if __name__ == "__main__":
    unittest.main()
