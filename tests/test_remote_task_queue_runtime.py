import copy
import os
import sys
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from remote_task_queue_runtime import (
    claim_remote, complete_remote, enqueue_remote, recover_remote, resolve_superseded_dead_letters,
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
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {"id": "workflow_auto_sync", "capabilities": ["deterministic_audit"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 1, "timeout_seconds": 300}},
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

    def manual_payload(self, idem="production:manual-authorized:fp:123"):
        return self.payload(
            idempotency_key=idem,
            requester_program_id="workflow_automation_watchdog",
            target_program_id="workflow_auto_sync",
            capability="deterministic_audit",
            input={
                "production_decision": "USER_AUTHORIZED_MANUAL_AUDIT",
                "production_fingerprint": "fp",
                "authorization_run_id": "123",
                "authorization_run_attempt": "1",
                "authorization_actor": "maintainer",
                "authorization_actor_id": "678",
                "authorization_repository": "instarrys-bit/default",
                "authorization_workflow_ref": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
                "authorization_event": "workflow_dispatch",
                "authorization_ref": "refs/heads/main",
                "authorization_head_sha": "a" * 40,
                "authorization_requested": True,
                "authorization_target_program_id": "workflow_auto_sync",
                "authorization_idempotency_key": idem,
                "baseline_source_event": "workflow_dispatch",
                "baseline_source_sha": "a" * 40,
            },
        )

    def test_manual_enqueue_requires_trusted_watchdog_dispatch_context(self):
        env = {
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_WORKFLOW_REF": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": "maintainer",
            "GITHUB_ACTOR_ID": "678", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40, "GITHUB_MANUAL_AUDIT_REQUEST": "true",
        }
        payload = self.manual_payload()
        with patch.dict(os.environ, env, clear=True):
            created = enqueue_remote(payload, self.store, self.registry, self.now)
            replayed = enqueue_remote(payload, self.store, self.registry, self.now)
        self.assertTrue(created["created"])
        self.assertFalse(replayed["created"])
        self.assertEqual(created["task"]["task_id"], replayed["task"]["task_id"])
        record = self.store.document["manual_authorizations"]["123"]
        self.assertEqual(record["task_id"], created["task"]["task_id"])
        self.assertEqual(record["target_program_id"], "workflow_auto_sync")
        self.assertEqual(record["idempotency_key"], payload["idempotency_key"])
        self.assertEqual(len(record["scope_sha256"]), 64)

        replay = dict(env)
        replay["GITHUB_RUN_ATTEMPT"] = "2"
        with patch.dict(os.environ, replay, clear=True):
            with self.assertRaisesRegex(ValueError, "authorization_run_attempt"):
                self.claim("worker-replay", self.now)

    def test_manual_authorization_run_can_be_consumed_by_only_one_task(self):
        env = {
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_WORKFLOW_REF": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": "maintainer",
            "GITHUB_ACTOR_ID": "678", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40, "GITHUB_MANUAL_AUDIT_REQUEST": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            enqueue_remote(self.manual_payload(), self.store, self.registry, self.now)
            with self.assertRaisesRegex(ValueError, "already been consumed"):
                enqueue_remote(
                    self.manual_payload("production:manual-authorized:fp:123:second"),
                    self.store, self.registry, self.now,
                )

    def test_manual_authorization_ledger_must_match_the_task(self):
        env = {
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_WORKFLOW_REF": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": "maintainer",
            "GITHUB_ACTOR_ID": "678", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40, "GITHUB_MANUAL_AUDIT_REQUEST": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            enqueue_remote(self.manual_payload(), self.store, self.registry, self.now)
            self.store.document["manual_authorizations"]["123"]["target_program_id"] = "script_target"
            with self.assertRaisesRegex(ValueError, "consumption record"):
                self.claim("worker-tamper", self.now)

    def test_manual_enqueue_rejects_non_dispatch_or_wrong_workflow(self):
        env = {
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_WORKFLOW_REF": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "GITHUB_EVENT_NAME": "schedule", "GITHUB_ACTOR": "maintainer", "GITHUB_MANUAL_AUDIT_REQUEST": "true",
            "GITHUB_ACTOR_ID": "678", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
        }
        payload = self.payload(input={
            "production_decision": "USER_AUTHORIZED_MANUAL_AUDIT",
            "production_fingerprint": "fp", "authorization_run_id": "123",
            "authorization_run_attempt": "1", "authorization_actor": "maintainer",
            "authorization_actor_id": "678", "authorization_repository": "instarrys-bit/default",
            "authorization_workflow_ref": env["GITHUB_WORKFLOW_REF"],
            "authorization_event": "workflow_dispatch", "authorization_ref": "refs/heads/main",
            "authorization_head_sha": "a" * 40, "authorization_requested": True, "baseline_source_event": "workflow_dispatch",
            "baseline_source_sha": "a" * 40,
        })
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "workflow_dispatch"):
                enqueue_remote(payload, self.store, self.registry, self.now)

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
        task = self.claim("worker-a", self.now)
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
        first = self.claim("worker-a", self.now)
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
        task = self.claim("worker-a", self.now)
        recovered = recover_remote(self.store, self.registry, self.now + timedelta(seconds=121))
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["task_id"], task["task_id"])
        self.assertEqual(recovered[0]["status"], "QUEUED")

    def test_resource_contract_is_claimed_atomically_and_held_through_verification(self):
        enqueue_remote(self.payload(), self.store, self.registry, self.now)
        eligible = {task["task_id"] for task in self.store.document["tasks"]}
        task = claim_remote(
            "worker-a", self.store, self.registry, eligible_task_ids=eligible,
            resource_keys_by_target={"script_target": {
                "resource_keys": ["rulesets/direct.list", "rulesets/manifest.json"],
                "lease_seconds": 60,
            }},
            now=self.now,
        )
        self.assertEqual(task["resource_lease"]["status"], "ACTIVE")
        proof = task["resource_lease"]["resources"]
        self.assertEqual(set(proof), {"rulesets/direct.list", "rulesets/manifest.json"})
        done = complete_remote(task["task_id"], "worker-a", task["lease"]["token"],
                               success=True, result={"run_id": 1}, store=self.store,
                               registry=self.registry, now=self.now)
        self.assertEqual(done["status"], "VERIFYING")
        for key, item in proof.items():
            record = self.store.document["resource_leases"][key]
            self.assertEqual(record["status"], "ACTIVE")
            self.assertEqual(record["fencing_token"], item["fencing_token"])

    def test_resource_conflict_leaves_task_queued_without_partial_claim(self):
        enqueue_remote(self.payload(idempotency_key="first"), self.store, self.registry, self.now)
        enqueue_remote(self.payload(idempotency_key="second"), self.store, self.registry, self.now)
        keys = {"script_target": {"resource_keys": ["rulesets/manifest.json"], "lease_seconds": 60}}
        first_id = self.store.document["tasks"][0]["task_id"]
        first = claim_remote("worker-a", self.store, self.registry,
                             eligible_task_ids={first_id}, resource_keys_by_target=keys, now=self.now)
        self.assertIsNotNone(first)
        second_id = next(x["task_id"] for x in self.store.document["tasks"] if x["task_id"] != first_id)
        blocked = claim_remote("worker-b", self.store, self.registry,
                               eligible_task_ids={second_id}, resource_keys_by_target=keys, now=self.now)
        self.assertIsNone(blocked)
        second = next(x for x in self.store.document["tasks"] if x["task_id"] == second_id)
        self.assertEqual(second["status"], "QUEUED")
        self.assertEqual(second["attempts"], 0)
        self.assertIsNone(second["lease"])

    def test_failed_task_releases_its_resource_lease(self):
        enqueue_remote(self.payload(), self.store, self.registry, self.now)
        task_id = self.store.document["tasks"][0]["task_id"]
        task = claim_remote("worker-a", self.store, self.registry,
                            eligible_task_ids={task_id},
                            resource_keys_by_target={"script_target": {
                                "resource_keys": ["rulesets/manifest.json"], "lease_seconds": 60}},
                            now=self.now)
        failed = complete_remote(task_id, "worker-a", task["lease"]["token"],
                                 success=False, error={"type": "test"}, store=self.store,
                                 registry=self.registry, now=self.now)
        self.assertEqual(failed["status"], "QUEUED")
        record = self.store.document["resource_leases"]["rulesets/manifest.json"]
        self.assertEqual(record["status"], "RELEASED")
        self.assertEqual(record["fencing_token"], task["resource_lease"]["resources"]["rulesets/manifest.json"]["fencing_token"])

    def create_dead_letter_auto_sync(self, source_sha, idempotency_key):
        created = enqueue_remote(self.payload(
            idempotency_key=idempotency_key,
            requester_program_id="workflow_automation_watchdog",
            target_program_id="workflow_auto_sync",
            capability="deterministic_audit",
            input={"baseline_source_event": "push", "baseline_source_sha": source_sha},
        ), self.store, self.registry, self.now)
        task_id = created["task"]["task_id"]
        claimed = claim_remote("watchdog-worker", self.store, self.registry,
                               eligible_task_ids={task_id}, now=self.now)
        return complete_remote(
            task_id, "watchdog-worker", claimed["lease"]["token"],
            success=False,
            error={"type": "workflow_run_failed", "message": "old workflow failed",
                   "evidence": {"status": "completed", "conclusion": "failure", "run_id": 456}},
            store=self.store, registry=self.registry, now=self.now,
        )

    def test_superseded_dead_letter_is_cancelled_with_auditable_resolution(self):
        old_sha, current_sha = "a" * 40, "b" * 40
        task = self.create_dead_letter_auto_sync(old_sha, "production:old-main:1")
        self.assertEqual(task["status"], "DEAD_LETTER")
        resolved = resolve_superseded_dead_letters(self.store, self.registry, current_sha, self.now)
        self.assertEqual([item["task_id"] for item in resolved], [task["task_id"]])
        saved = self.store.document["tasks"][0]
        self.assertEqual(saved["status"], "CANCELLED")
        self.assertEqual(saved["state_history"][-2:], ["DEAD_LETTER", "CANCELLED"])
        self.assertEqual(saved["resolution"]["disposition"], "superseded")
        self.assertEqual(saved["resolution"]["superseded_by_main_sha"], current_sha)
        self.assertEqual(saved["resolution"]["evidence"]["original_source_sha"], old_sha)
        self.assertEqual(resolve_superseded_dead_letters(self.store, self.registry, current_sha, self.now), [])

    def test_dead_letter_for_current_main_is_not_superseded(self):
        current_sha = "c" * 40
        self.create_dead_letter_auto_sync(current_sha, "production:current-main:1")
        self.assertEqual(resolve_superseded_dead_letters(self.store, self.registry, current_sha, self.now), [])
        self.assertEqual(self.store.document["tasks"][0]["status"], "DEAD_LETTER")

    def test_unknown_dispatch_outcome_is_not_superseded(self):
        old_sha = "d" * 40
        task = self.create_dead_letter_auto_sync(old_sha, "production:unknown:1")
        task["last_error"]["evidence"]["status"] = "unknown"
        self.store.document["tasks"][0] = task
        self.assertEqual(resolve_superseded_dead_letters(self.store, self.registry, "e" * 40, self.now), [])
        self.assertEqual(self.store.document["tasks"][0]["status"], "DEAD_LETTER")

    def test_empty_claim_and_recovery_do_not_write(self):
        self.assertIsNone(self.claim("worker-a", self.now))
        self.assertEqual(recover_remote(self.store, self.registry, self.now), [])
        self.assertEqual(self.store.writes, 0)



    def test_expired_manual_task_is_dead_lettered_without_reusing_its_grant(self):
        env = {
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_WORKFLOW_REF": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": "maintainer",
            "GITHUB_ACTOR_ID": "678", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40, "GITHUB_MANUAL_AUDIT_REQUEST": "true",
        }
        with patch.dict(os.environ, env, clear=True):
            created = enqueue_remote(self.manual_payload(), self.store, self.registry, self.now)
            claimed = self.claim("manual-worker", self.now)
        self.assertEqual(claimed["task_id"], created["task"]["task_id"])
        recovered = recover_remote(self.store, self.registry, self.now + timedelta(seconds=301))
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["status"], "DEAD_LETTER")
        self.assertEqual(recovered[0]["attempts"], 1)
        self.assertEqual(self.store.document["manual_authorizations"]["123"]["task_id"], claimed["task_id"])
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "already been consumed"):
                enqueue_remote(
                    self.manual_payload("production:manual-authorized:fp:123:after-expiry"),
                    self.store, self.registry, self.now + timedelta(seconds=302),
                )

if __name__ == "__main__":
    unittest.main(verbosity=2)
