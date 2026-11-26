import copy
import json
import sys
import unittest
from unittest.mock import Mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "storage" / "v2"))

from runtime import (
    Conflict, GitHubSegmentedBackend, append_event, assert_automation_write_allowed,
    canonical_bytes, empty_state, project, sha256, validate_state,
)


class StorageV2Tests(unittest.TestCase):
    def setUp(self):
        self.state = empty_state("test-epoch")

    def append(self, kind, payload, key, revision=None, created_at="2026-11-17T00:00:00Z"):
        candidate, result = append_event(
            self.state, event_type=kind, payload=payload, actor="test",
            idempotency_key=key,
            expected_revision=self.state["revision"] if revision is None else revision,
            created_at=created_at,
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
        claimed, _ = append_event(queued, event_type="TASK_CLAIMED",
            payload={"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"},
            actor="test", idempotency_key="claim", expected_revision=1,
            created_at="2026-11-17T00:00:00Z")
        with self.assertRaisesRegex(ValueError, "invalid task transition"):
            append_event(claimed, event_type="TASK_SUCCEEDED",
                payload={"task_id":"task-1","result_artifact_id":"sha","lease_id":"tl1","owner":"worker","token":"t1"},
                actor="test", idempotency_key="k", expected_revision=2,
                created_at="2026-11-17T00:01:00Z")

    def test_resource_fencing_tokens_increase(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enqueue")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"task-lease","owner":"worker","token":"task-token","expires_at":"2026-11-17T00:30:00Z"}, "claim")
        self.append("RESOURCE_ACQUIRED", {"resource_key":"rulesets/direct.list","lease_id":"l1","task_id":"task-1","owner":"worker","fencing_token":1,"expires_at":"2026-11-17T00:10:00Z"}, "resource-1")
        self.append("RESOURCE_RELEASED", {"resource_key":"rulesets/direct.list","lease_id":"l1","fencing_token":1}, "resource-2")
        self.append("RESOURCE_ACQUIRED", {"resource_key":"rulesets/direct.list","lease_id":"l2","task_id":"task-1","owner":"worker","fencing_token":2,"expires_at":"2026-11-17T00:20:00Z"}, "resource-3")
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
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed("rulesets/direct.list", "watchdog")
        self.assertIsNone(assert_automation_write_allowed("rulesets/direct.list", "storage_management"))

    def test_storage_manager_has_narrow_exact_write_scope(self):
        allowed = [
            "storage/v2/state.json",
            "storage/v2/state/manifest.json",
            "storage/v2/state/segments/segment-00000001.jsonl",
            "storage/v2/artifacts/sha256/" + "a" * 64,
            "storage/v2/migration/manifests/" + "b" * 64 + ".json",
            "storage/v2/projections/queue.json",
            "storage/v2/releases/" + "c" * 64 + ".json",
            "rulesets/reject.list",
        ]
        for path in allowed:
            self.assertIsNone(assert_automation_write_allowed(path, "storage_management"), path)
        denied = [
            "storage/v2/queue_seed.json",
            "storage/v2/production_write_policy.json",
            "storage/v2/artifacts/sha256/not-a-digest",
            "automation/task_queue.json",
            "modules/uu.conf",
        ]
        for path in denied:
            with self.assertRaises(PermissionError, msg=path):
                assert_automation_write_allowed(path, "storage_management")
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed("storage/v2/state.json", "watchdog")

    def test_machine_policy_matches_automation_only_config_boundary(self):
        policy_path = ROOT / "storage/v2/production_write_policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        config = next(item for item in policy["protected_paths"] if item["path"] == "modules/uu.conf")
        self.assertEqual(config["scope"], "AUTOMATED_WORKFLOWS_AND_AUTOMATION_IDENTITIES_ONLY")
        self.assertEqual(policy["enforcement"]["protection_scope"], "automation_identities_only")
        self.assertTrue(policy["enforcement"]["manual_user_edits_allowed"])
        manager_writes = policy["actors"]["storage_management"]["write"]
        self.assertIn("storage/v2/state.json", manager_writes)
        self.assertIn("storage/v2/state/manifest.json", manager_writes)
        self.assertIn("storage/v2/state/segments/*.jsonl", manager_writes)
        self.assertNotIn("storage/v2/queue_seed.json", manager_writes)
        self.assertNotIn("storage/v2/production_write_policy.json", manager_writes)


    def _claimed_task_with_resource(self, resource_expiry="2026-11-17T00:10:00Z"):
        self.append("TASK_ENQUEUED", {"task_id":"task-lease","max_attempts":3}, "enqueue-lease")
        self.append("TASK_CLAIMED", {"task_id":"task-lease","lease_id":"task-l1","owner":"worker","token":"task-t1","expires_at":"2026-11-17T00:30:00Z"}, "claim-lease")
        self.append("RESOURCE_ACQUIRED", {"resource_key":"rulesets/direct.list","lease_id":"res-l1","task_id":"task-lease","owner":"worker","fencing_token":1,"expires_at":resource_expiry}, "acquire-resource")

    def test_task_lease_renewal_extends_live_lease(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        self.append("TASK_LEASE_RENEWED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:20:00Z"}, "renew", created_at="2026-11-17T00:05:00Z")
        lease = project(self.state)["tasks"]["task-1"]["task_lease"]
        self.assertEqual(lease["expires_at"], "2026-11-17T00:20:00Z")
        self.assertEqual(lease["status"], "ACTIVE")

    def test_expired_task_lease_cannot_be_renewed(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        with self.assertRaisesRegex(Conflict, "expired task lease"):
            self.append("TASK_LEASE_RENEWED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:20:00Z"}, "late-renew", created_at="2026-11-17T00:11:00Z")

    def test_task_lease_expiry_requires_elapsed_deadline(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        with self.assertRaisesRegex(ValueError, "before its expiry"):
            self.append("TASK_LEASE_EXPIRED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1"}, "early-expire", created_at="2026-11-17T00:09:00Z")
        self.append("TASK_LEASE_EXPIRED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1"}, "expire", created_at="2026-11-17T00:11:00Z")
        self.assertEqual(project(self.state)["tasks"]["task-1"]["task_lease"]["status"], "EXPIRED")

    def test_resource_lease_renew_expire_and_reacquire_increments_fence(self):
        self._claimed_task_with_resource()
        self.append("RESOURCE_LEASE_RENEWED", {"resource_key":"rulesets/direct.list","lease_id":"res-l1","task_id":"task-lease","owner":"worker","fencing_token":1,"expires_at":"2026-11-17T00:20:00Z"}, "renew-resource", created_at="2026-11-17T00:05:00Z")
        self.append("RESOURCE_LEASE_EXPIRED", {"resource_key":"rulesets/direct.list","lease_id":"res-l1","fencing_token":1}, "expire-resource", created_at="2026-11-17T00:21:00Z")
        self.assertEqual(project(self.state)["resource_leases"]["rulesets/direct.list"]["status"], "EXPIRED")
        self.append("RESOURCE_ACQUIRED", {"resource_key":"rulesets/direct.list","lease_id":"res-l2","task_id":"task-lease","owner":"worker","fencing_token":2,"expires_at":"2026-11-17T00:25:00Z"}, "reacquire-resource", created_at="2026-11-17T00:22:00Z")
        self.assertEqual(project(self.state)["resource_leases"]["rulesets/direct.list"]["fencing_token"], 2)

    def test_resource_lease_cannot_be_expired_early(self):
        self._claimed_task_with_resource()
        with self.assertRaisesRegex(ValueError, "before its expiry"):
            self.append("RESOURCE_LEASE_EXPIRED", {"resource_key":"rulesets/direct.list","lease_id":"res-l1","fencing_token":1}, "early-resource-expire", created_at="2026-11-17T00:09:00Z")

    def test_resource_lease_renewal_cannot_outlive_task_lease(self):
        self._claimed_task_with_resource()
        with self.assertRaisesRegex(ValueError, "cannot outlive"):
            self.append("RESOURCE_LEASE_RENEWED", {"resource_key":"rulesets/direct.list","lease_id":"res-l1","task_id":"task-lease","owner":"worker","fencing_token":1,"expires_at":"2026-11-17T00:31:00Z"}, "overrun-resource", created_at="2026-11-17T00:05:00Z")

    def test_stale_resource_fencing_token_cannot_renew(self):
        self._claimed_task_with_resource()
        with self.assertRaisesRegex(Conflict, "fencing token mismatch"):
            self.append("RESOURCE_LEASE_RENEWED", {"resource_key":"rulesets/direct.list","lease_id":"res-l1","task_id":"task-lease","owner":"worker","fencing_token":2,"expires_at":"2026-11-17T00:20:00Z"}, "stale-resource-renew", created_at="2026-11-17T00:05:00Z")

    def test_task_requeue_waits_until_resource_lease_is_expired_or_released(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        self.append("RESOURCE_ACQUIRED", {"resource_key":"rulesets/direct.list","lease_id":"rl1","task_id":"task-1","owner":"worker","fencing_token":1,"expires_at":"2026-11-17T00:08:00Z"}, "resource")
        self.append("TASK_LEASE_EXPIRED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1"}, "task-expire", created_at="2026-11-17T00:11:00Z")
        with self.assertRaisesRegex(ValueError, "release task resource leases"):
            self.append("TASK_REQUEUED", {"task_id":"task-1","reason":"worker timeout","lease_id":"tl1","owner":"worker","token":"t1"}, "requeue", created_at="2026-11-17T00:12:00Z")
        self.append("RESOURCE_LEASE_EXPIRED", {"resource_key":"rulesets/direct.list","lease_id":"rl1","fencing_token":1}, "resource-expire", created_at="2026-11-17T00:11:00Z")
        self.append("TASK_REQUEUED", {"task_id":"task-1","reason":"worker timeout","lease_id":"tl1","owner":"worker","token":"t1"}, "requeue-after-expiry", created_at="2026-11-17T00:12:00Z")
        self.assertEqual(project(self.state)["tasks"]["task-1"]["status"], "QUEUED")


    def test_task_requeue_rejects_still_active_task_lease(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        with self.assertRaisesRegex(Conflict, "expired or released"):
            self.append("TASK_REQUEUED", {"task_id":"task-1","reason":"worker timeout","lease_id":"tl1","owner":"worker","token":"t1"}, "requeue-active", created_at="2026-11-17T00:05:00Z")


    def test_worker_task_completion_requires_matching_active_lease_token(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        with self.assertRaisesRegex(Conflict, "lease identity or token mismatch"):
            self.append("TASK_SUCCEEDED", {"task_id":"task-1","result_artifact_id":"sha256:abc","lease_id":"tl1","owner":"worker","token":"stale"}, "stale-success", created_at="2026-11-17T00:05:00Z")

    def test_worker_cannot_complete_after_task_lease_expiry(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":2}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        self.append("TASK_LEASE_EXPIRED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1"}, "expire", created_at="2026-11-17T00:11:00Z")
        with self.assertRaisesRegex(Conflict, "lease identity or token mismatch"):
            self.append("TASK_SUCCEEDED", {"task_id":"task-1","result_artifact_id":"sha256:abc","lease_id":"tl1","owner":"worker","token":"t1"}, "late-success", created_at="2026-11-17T00:12:00Z")


    def test_active_task_lease_cannot_be_dead_lettered(self):
        self.append("TASK_ENQUEUED", {"task_id":"task-1","max_attempts":1}, "enq")
        self.append("TASK_CLAIMED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1","expires_at":"2026-11-17T00:10:00Z"}, "claim")
        with self.assertRaisesRegex(Conflict, "must expire or be released"):
            self.append("TASK_DEAD_LETTER", {"task_id":"task-1","reason":"retry budget exhausted"}, "dead-letter-live", created_at="2026-11-17T00:05:00Z")
        self.append("TASK_LEASE_EXPIRED", {"task_id":"task-1","lease_id":"tl1","owner":"worker","token":"t1"}, "expire", created_at="2026-11-17T00:11:00Z")
        self.append("TASK_DEAD_LETTER", {"task_id":"task-1","reason":"retry budget exhausted"}, "dead-letter-expired", created_at="2026-11-17T00:12:00Z")
        self.assertEqual(project(self.state)["tasks"]["task-1"]["status"], "DEAD_LETTER")

    def test_artifact_catalog_is_storage_management_only_and_allowlisted(self):
        assert_automation_write_allowed(
            "storage/v2/artifacts/catalog/123456789.json", "storage_management"
        )
        assert_automation_write_allowed(
            "storage/v2/artifacts/sha256/" + "a" * 64, "storage_management"
        )
        with self.assertRaises(PermissionError):
            assert_automation_write_allowed(
                "storage/v2/artifacts/catalog/123456789.json", "production_worker"
            )
        with self.assertRaises(ValueError):
            assert_automation_write_allowed(
                "storage/v2/artifacts/catalog/../task_queue.json", "storage_management"
            )

    def test_segmented_manifest_and_event_chain_are_verified_on_read(self):
        backend = GitHubSegmentedBackend("owner/repo", "main", "token")
        state, _ = append_event(
            self.state, event_type="TASK_ENQUEUED",
            payload={"task_id": "task-1", "max_attempts": 2},
            actor="test", idempotency_key="enqueue-1", expected_revision=0,
            created_at="2026-11-17T00:00:00Z",
        )
        raw = canonical_bytes(state["events"][0]) + b"\\n"
        record = {
            "index": 1, "path": "storage/v2/state/segments/segment-00000001.jsonl",
            "first_sequence": 1, "last_sequence": 1, "record_count": 1,
            "byte_count": len(raw), "sha256": sha256(raw), "git_blob_sha": "segment-blob",
        }
        unsigned = {
            "schema_version": 1, "epoch_id": state["epoch_id"], "revision": 1,
            "total_event_count": 1, "segment_count": 1,
            "last_event_sha256": state["events"][-1]["event_sha256"],
            "created_at": state["created_at"], "updated_at": state["created_at"],
            "segments": [record],
        }
        manifest = dict(unsigned)
        manifest["manifest_sha256"] = sha256(canonical_bytes(unsigned))
        manifest_raw = json.dumps(manifest, sort_keys=True).encode("utf-8")
        backend._tree_entry = Mock(side_effect=[
            {"type": "blob", "sha": "manifest-blob"},
            {"type": "tree", "sha": "segment-directory"},
        ])
        backend._request = Mock(return_value={
            "tree": [{"path": "segment-00000001.jsonl", "type": "blob", "sha": "segment-blob"}]
        })
        backend._read_blob = Mock(side_effect=lambda sha: manifest_raw if sha == "manifest-blob" else raw)
        restored, _, _, legacy = backend._read_at_head("head-sha", "root-tree")
        self.assertFalse(legacy)
        self.assertEqual(restored, state)

    def test_segmented_backend_rejects_stale_head_token_before_any_write(self):
        backend = GitHubSegmentedBackend("owner/repo", "main", "token")
        current, _ = append_event(
            self.state, event_type="TASK_ENQUEUED",
            payload={"task_id": "task-1", "max_attempts": 2},
            actor="test", idempotency_key="enqueue-1", expected_revision=0,
        )
        candidate, _ = append_event(
            current, event_type="TASK_CLAIMED",
            payload={"task_id": "task-1", "lease_id": "lease-1", "owner": "worker",
                     "token": "t1", "expires_at": "2026-11-17T00:10:00Z"},
            actor="test", idempotency_key="claim-1", expected_revision=1,
        )
        backend._head_and_tree = Mock(return_value=("current-head", "tree"))
        backend._read_at_head = Mock(return_value=(current, None, [], False))
        backend._request = Mock()
        with self.assertRaises(Conflict):
            backend.compare_and_swap(
                candidate, expected_revision=1, expected_blob_sha="stale-head",
                message="test stale CAS",
            )
        backend._request.assert_not_called()

    def test_segmented_backend_initial_commit_uses_non_force_ref_update(self):
        backend = GitHubSegmentedBackend("owner/repo", "main", "token")
        backend._head_and_tree = Mock(return_value=("base-head", "base-tree"))
        backend._read_at_head = Mock(return_value=(None, None, [], False))
        backend._create_blob = Mock(return_value="manifest-blob")
        backend._request = Mock(side_effect=[
            {"sha": "new-tree"}, {"sha": "new-commit"}, {},
        ])
        backend.read = Mock(return_value=(self.state, "new-commit"))
        result = backend.compare_and_swap(
            self.state, expected_revision=-1, expected_blob_sha=None,
            message="initialize segmented log",
        )
        self.assertEqual(result, "new-commit")
        patch_calls = [call for call in backend._request.call_args_list if call.args[0] == "PATCH"]
        self.assertEqual(len(patch_calls), 1)
        self.assertFalse(patch_calls[0].args[2]["force"])


if __name__ == "__main__":
    unittest.main()
