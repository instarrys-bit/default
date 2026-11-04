import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import resource_lease_runtime
from resource_lease_runtime import (
    acquire_resource_leases, assert_resource_lease, release_resource_leases,
    normalize_keys, renew_resource_leases_in_queue, assert_workflow_resource_lease,
    assert_resource_lease_from_environment,
)


class MemoryStore:
    def __init__(self, document):
        self.document = copy.deepcopy(document)

    def mutate(self, mutator):
        candidate, result = mutator(copy.deepcopy(self.document))
        self.document = copy.deepcopy(candidate)
        return copy.deepcopy(result)


def queue_with_task(task_id, worker, token, expiry):
    return {
        "schema_version": 1,
        "revision": 0,
        "tasks": [{
            "task_id": task_id,
            "status": "CLAIMED",
            "lease": {"owner": worker, "token": token, "expires_at": expiry},
        }],
    }


class ResourceLeaseRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        expiry = (self.now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        self.store = MemoryStore(queue_with_task("task_a", "worker_a", "task-token-a", expiry))

    def test_acquires_sorted_resources_and_fencing_asserts(self):
        result = acquire_resource_leases(
            "task_a", "worker_a", "task-token-a",
            ["rulesets/manifest.json", "rulesets/direct.list"], self.store,
            now=self.now,
        )
        self.assertTrue(result["acquired"])
        self.assertEqual(list(result["resources"]), ["rulesets/direct.list", "rulesets/manifest.json"])
        for key, token in result["resources"].items():
            self.assertTrue(assert_resource_lease(
                self.store.document, task_id="task_a", worker_id="worker_a",
                task_lease_token="task-token-a", resource_path=key,
                lease_id=token["lease_id"], fencing_token=token["fencing_token"],
                now=self.now,
            ))

    def test_conflict_acquires_none_of_a_multi_resource_request(self):
        acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                ["rulesets/direct.list"], self.store, now=self.now)
        expiry = (self.now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        self.store.document["tasks"].append({
            "task_id": "task_b", "status": "CLAIMED",
            "lease": {"owner": "worker_b", "token": "task-token-b", "expires_at": expiry},
        })
        result = acquire_resource_leases("task_b", "worker_b", "task-token-b",
                                         ["reports/new.json", "rulesets/direct.list"],
                                         self.store, now=self.now)
        self.assertFalse(result["acquired"])
        self.assertEqual(result["blocked_resource"], "rulesets/direct.list")
        self.assertNotIn("reports/new.json", self.store.document["resource_leases"])

    def test_expired_lease_takeover_increments_fencing_token(self):
        first = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                        ["rulesets/manifest.json"], self.store, now=self.now)
        old = self.store.document["resource_leases"]["rulesets/manifest.json"]
        old["expires_at"] = (self.now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        expiry = (self.now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        self.store.document["tasks"].append({
            "task_id": "task_b", "status": "CLAIMED",
            "lease": {"owner": "worker_b", "token": "task-token-b", "expires_at": expiry},
        })
        second = acquire_resource_leases("task_b", "worker_b", "task-token-b",
                                         ["rulesets/manifest.json"], self.store, now=self.now)
        self.assertTrue(second["acquired"])
        self.assertEqual(second["resources"]["rulesets/manifest.json"]["fencing_token"],
                         first["resources"]["rulesets/manifest.json"]["fencing_token"] + 1)
        with self.assertRaisesRegex(ValueError, "fencing check failed"):
            assert_resource_lease(self.store.document, task_id="task_a", worker_id="worker_a",
                                  task_lease_token="task-token-a", resource_path="rulesets/manifest.json",
                                  lease_id=first["resources"]["rulesets/manifest.json"]["lease_id"],
                                  fencing_token=first["resources"]["rulesets/manifest.json"]["fencing_token"],
                                  now=self.now)

    def test_stale_owner_cannot_release_new_lease(self):
        first = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                        ["rulesets/direct.list"], self.store, now=self.now)
        record = self.store.document["resource_leases"]["rulesets/direct.list"]
        record["expires_at"] = (self.now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        expiry = (self.now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        self.store.document["tasks"].append({
            "task_id": "task_b", "status": "CLAIMED",
            "lease": {"owner": "worker_b", "token": "task-token-b", "expires_at": expiry},
        })
        second = acquire_resource_leases("task_b", "worker_b", "task-token-b",
                                         ["rulesets/direct.list"], self.store, now=self.now)
        with self.assertRaisesRegex(ValueError, "stale or mismatched"):
            release_resource_leases("task_a", "worker_a", "task-token-a",
                                    first["resources"], self.store, now=self.now)
        self.assertEqual(self.store.document["resource_leases"]["rulesets/direct.list"]["lease_id"],
                         second["resources"]["rulesets/direct.list"]["lease_id"])

    def test_release_preserves_fencing_counter(self):
        acquired = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                           ["rulesets/direct.list"], self.store, now=self.now)
        released = release_resource_leases("task_a", "worker_a", "task-token-a",
                                           acquired["resources"], self.store, now=self.now)
        self.assertTrue(released["fencing_counters_preserved"])
        record = self.store.document["resource_leases"]["rulesets/direct.list"]
        self.assertEqual(record["status"], "RELEASED")
        self.assertEqual(record["fencing_token"], acquired["resources"]["rulesets/direct.list"]["fencing_token"])

    def test_reacquiring_same_active_lease_is_idempotent(self):
        first = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                        ["rulesets/direct.list"], self.store, now=self.now)
        second = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                         ["rulesets/direct.list"], self.store, now=self.now)
        self.assertEqual(first["resources"], second["resources"])

    def test_lease_renewal_extends_only_a_current_unexpired_fence(self):
        acquired = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                           ["rulesets/manifest.json"], self.store, now=self.now)
        task = self.store.document["tasks"][0]
        task["resource_lease"] = {
            "status": "ACTIVE", "resources": acquired["resources"],
            "lease_seconds": 300, "expires_at": acquired["expires_at"],
        }
        later = self.now + timedelta(seconds=20)
        self.assertTrue(renew_resource_leases_in_queue(self.store.document, task, later))
        record = self.store.document["resource_leases"]["rulesets/manifest.json"]
        self.assertEqual(record["expires_at"], (later + timedelta(seconds=300)).isoformat(timespec="seconds").replace("+00:00", "Z"))
        record["expires_at"] = (later - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        self.assertFalse(renew_resource_leases_in_queue(self.store.document, task, later))

    def test_workflow_publish_assertion_checks_current_fencing_epoch(self):
        acquired = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                           ["logical/production-pipeline"], self.store, now=self.now)
        task = self.store.document["tasks"][0]
        task["target_program_id"] = "workflow_auto_sync"
        task["requester_program_id"] = "workflow_automation_watchdog"
        task["attempts"] = 1
        task["dispatch_intent"] = {
            "task_id": "task_a", "dispatch_attempt": 1,
            "correlation_id": "task_a-a1",
            "workflow_path": ".github/workflows/auto_sync.yml", "ref": "main",
        }
        task["resource_lease"] = {
            "status": "ACTIVE", "resources": acquired["resources"],
            "lease_seconds": 300, "expires_at": acquired["expires_at"],
        }
        proof = acquired["resources"]
        result = assert_workflow_resource_lease(self.store.document, "task_a", proof, now=self.now)
        self.assertTrue(result["valid"])
        record = self.store.document["resource_leases"]["logical/production-pipeline"]
        record["fencing_token"] += 1
        with self.assertRaisesRegex(ValueError, "stale or fenced"):
            assert_workflow_resource_lease(self.store.document, "task_a", proof, now=self.now)

    def test_synchronous_child_checks_live_queue_fencing(self):
        acquired = acquire_resource_leases("task_a", "worker_a", "task-token-a",
                                           ["sources/source_assessments.json"], self.store, now=self.now)
        task = self.store.document["tasks"][0]
        task["resource_lease"] = {
            "status": "ACTIVE", "resources": acquired["resources"],
            "lease_seconds": 300, "expires_at": acquired["expires_at"],
        }
        proof = acquired["resources"]
        class LiveStore:
            def __init__(self, document):
                self.document = copy.deepcopy(document)
            def read(self):
                return type("Snapshot", (), {"document": copy.deepcopy(self.document)})()
        live = LiveStore(self.store.document)
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "queue.json"
            snapshot.write_text(json.dumps(self.store.document), encoding="utf-8")
            env = {
                "AUTOMATION_QUEUE_SNAPSHOT": str(snapshot),
                "AUTOMATION_QUEUE_REPOSITORY": "owner/repo",
                "AUTOMATION_QUEUE_TOKEN": "read-token",
                "AUTOMATION_QUEUE_BRANCH": "main",
                "AUTOMATION_QUEUE_PATH": "automation/task_queue.json",
                "AUTOMATION_TASK_ID": "task_a",
                "AUTOMATION_WORKER_ID": "worker_a",
                "AUTOMATION_TASK_LEASE_TOKEN": "task-token-a",
                "AUTOMATION_RESOURCE_LEASE_PROOF": json.dumps(proof),
            }
            with patch.dict("os.environ", env, clear=False):
                with patch.object(resource_lease_runtime, "GitHubContentsQueueStore", return_value=live):
                    self.assertTrue(assert_resource_lease_from_environment("sources/source_assessments.json"))
                    live.document["resource_leases"]["sources/source_assessments.json"]["fencing_token"] += 1
                    with self.assertRaisesRegex(ValueError, "fencing check failed"):
                        assert_resource_lease_from_environment("sources/source_assessments.json")


    def test_rejects_path_traversal_and_noncanonical_paths(self):
        for value in ["../secret", "/etc/passwd", "rulesets//direct.list", "rulesets/../secret", " rulesets/direct.list"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_keys([value])

    def test_workflow_auto_sync_verifying_task_fences_every_repo_write_under_pipeline_lock(self):
        acquired = acquire_resource_leases(
            "task_a", "worker_a", "task-token-a",
            ["logical/production-pipeline"], self.store, now=self.now,
        )
        task = self.store.document["tasks"][0]
        task["status"] = "VERIFYING"
        task["target_program_id"] = "workflow_auto_sync"
        task["requester_program_id"] = "workflow_automation_watchdog"
        task["attempts"] = 1
        task["dispatch_intent"] = {
            "task_id": "task_a", "dispatch_attempt": 1,
            "correlation_id": "task_a-a1",
            "workflow_path": ".github/workflows/auto_sync.yml", "ref": "main",
        }
        task["resource_lease"] = {
            "status": "ACTIVE", "resources": acquired["resources"],
            "lease_seconds": 300, "expires_at": acquired["expires_at"],
        }
        proof = acquired["resources"]

        class LiveStore:
            def __init__(self, document):
                self.document = copy.deepcopy(document)
            def read(self):
                return type("Snapshot", (), {"document": copy.deepcopy(self.document)})()

        live = LiveStore(self.store.document)
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "queue.json"
            snapshot.write_text(json.dumps(self.store.document), encoding="utf-8")
            env = {
                "AUTOMATION_QUEUE_SNAPSHOT": str(snapshot),
                "AUTOMATION_QUEUE_REPOSITORY": "owner/repo",
                "AUTOMATION_QUEUE_TOKEN": "read-token",
                "AUTOMATION_QUEUE_BRANCH": "main",
                "AUTOMATION_QUEUE_PATH": "automation/task_queue.json",
                "AUTOMATION_TASK_ID": "task_a",
                "AUTOMATION_WORKER_ID": "worker_a",
                "AUTOMATION_TASK_LEASE_TOKEN": "task-token-a",
                "AUTOMATION_RESOURCE_LEASE_PROOF": json.dumps(proof),
            }
            with patch.dict("os.environ", env, clear=False):
                with patch.object(resource_lease_runtime, "GitHubContentsQueueStore", return_value=live):
                    self.assertTrue(assert_resource_lease_from_environment("reports/project-status.json"))
                    live.document["tasks"][0]["dispatch_intent"]["ref"] = "feature"
                    with self.assertRaisesRegex(ValueError, "exact Watchdog production dispatch"):
                        assert_resource_lease_from_environment("reports/project-status.json")


if __name__ == "__main__":
    unittest.main()
