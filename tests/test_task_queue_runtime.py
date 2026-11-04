import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from task_queue import validate_task_queue
from task_queue_runtime import (
    claim_next,
    complete_task,
    enqueue_task,
    recover_expired,
    validate_manual_authorization,
)


class TaskQueueRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "automation").mkdir()
        self.queue = self.root / "automation" / "task_queue.json"
        self.registry = self.root / "automation" / "program_registry.json"
        programs = [
            {"id": "script_requester", "capabilities": ["request"]},
            {
                "id": "script_target",
                "capabilities": ["test_capability"],
                "orchestration": {
                    "enabled": True,
                    "allowed_callers": ["script_requester"],
                    "max_attempts": 2,
                    "timeout_seconds": 120,
                },
            },
            {"id": "workflow_automation_watchdog", "capabilities": ["top_level_supervision"]},
            {
                "id": "workflow_auto_sync",
                "capabilities": ["deterministic_audit"],
                "orchestration": {
                    "enabled": True,
                    "allowed_callers": ["workflow_automation_watchdog"],
                    "max_attempts": 1,
                    "timeout_seconds": 300,
                },
            },
        ]
        self.registry.write_text(json.dumps({"programs": programs}), encoding="utf-8")
        self.queue.write_text(json.dumps({"schema_version": 1, "revision": 0, "tasks": []}), encoding="utf-8")
        self.now = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)

    def payload(self, **overrides):
        value = {
            "idempotency_key": "runtime:test:once",
            "trace_id": "trace-runtime-001",
            "requester_program_id": "script_requester",
            "target_program_id": "script_target",
            "capability": "test_capability",
            "priority": 50,
            "input": {"value": 1},
        }
        value.update(overrides)
        return value

    def enqueue(self, **overrides):
        return enqueue_task(self.payload(**overrides), self.queue, self.registry, self.now)

    def manual_authorization_task(self, **payload_overrides):
        idem = "production:manual-authorized:fp:123"
        payload = {
            "production_decision": "USER_AUTHORIZED_MANUAL_AUDIT",
            "production_fingerprint": "fp",
            "authorization_run_id": "123",
            "authorization_run_attempt": "2",
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
        }
        payload.update(payload_overrides)
        return {
            "idempotency_key": idem,
            "requester_program_id": "workflow_automation_watchdog",
            "target_program_id": "workflow_auto_sync",
            "capability": "deterministic_audit",
            "input": payload,
        }

    def manual_authorization_context(self):
        return {
            "repository": "instarrys-bit/default",
            "workflow_ref": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "event": "workflow_dispatch", "actor": "maintainer", "actor_id": "678",
            "run_id": "123", "run_attempt": "2", "ref": "refs/heads/main",
            "sha": "a" * 40, "manual_audit_requested": "true",
        }

    def test_manual_authorization_is_bound_to_exact_watchdog_run_attempt_and_task_scope(self):
        scope = validate_manual_authorization(
            self.manual_authorization_task(), self.manual_authorization_context()
        )
        self.assertEqual(scope["target_program_id"], "workflow_auto_sync")
        self.assertEqual(scope["idempotency_key"], "production:manual-authorized:fp:123")
        self.assertEqual(len(scope["scope_sha256"]), 64)

    def test_manual_authorization_rejects_replay_and_forged_identity(self):
        task = self.manual_authorization_task()
        context = self.manual_authorization_context()
        for key, value in (("run_id", "999"), ("run_attempt", "3"), ("actor_id", "1"),
                           ("event", "schedule"), ("ref", "refs/heads/feature"),
                           ("sha", "b" * 40), ("workflow_ref", "attacker/repo/.github/workflows/evil.yml@refs/heads/main")):
            altered = dict(context)
            altered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_manual_authorization(task, altered)

    def test_manual_authorization_rejects_target_or_idempotency_scope_mismatch(self):
        context = self.manual_authorization_context()
        task = self.manual_authorization_task(authorization_idempotency_key="different-key")
        with self.assertRaisesRegex(ValueError, "authorization_idempotency_key"):
            validate_manual_authorization(task, context)
        task = self.manual_authorization_task(
            authorization_target_program_id="script_target"
        )
        with self.assertRaisesRegex(ValueError, "workflow_auto_sync"):
            validate_manual_authorization(task, context)
        task = self.manual_authorization_task()
        task["target_program_id"] = "script_target"
        with self.assertRaisesRegex(ValueError, "scoped only"):
            validate_manual_authorization(task, context)

    def test_manual_authorization_rejects_incomplete_payload(self):
        with self.assertRaisesRegex(ValueError, "invalid or incomplete"):
            validate_manual_authorization({"input": {
                "production_decision": "RECOVERY_REQUIRED", "authorization_run_id": "123"
            }}, {})
        with self.assertRaisesRegex(ValueError, "trusted GitHub Actions run identity"):
            validate_manual_authorization({"input": {"production_decision": "USER_AUTHORIZED_MANUAL_AUDIT"}}, {})

    def test_non_manual_production_decisions_do_not_require_manual_authorization(self):
        validate_manual_authorization({"input": {
            "production_decision": "RECOVERY_REQUIRED",
            "production_reason": "bounded recovery"
        }}, {})

    def test_enqueue_is_idempotent(self):
        first = self.enqueue()
        second = self.enqueue()
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["task"]["task_id"], second["task"]["task_id"])
        self.assertEqual(len(json.loads(self.queue.read_text())["tasks"]), 1)

    def test_enqueue_rejects_disabled_or_unauthorized_target(self):
        data = json.loads(self.registry.read_text())
        data["programs"][1]["orchestration"]["enabled"] = False
        data["programs"][1]["orchestration"]["allowed_callers"] = []
        self.registry.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not enabled"):
            self.enqueue()

    def test_claim_uses_priority_and_only_claims_once(self):
        self.enqueue(idempotency_key="low", priority=10)
        self.enqueue(idempotency_key="high", priority=90)
        claimed = claim_next("worker-a", self.queue, self.registry, self.now)
        self.assertEqual(claimed["idempotency_key"], "high")
        self.assertEqual(claimed["attempts"], 1)
        self.assertEqual(claimed["status"], "CLAIMED")
        second = claim_next("worker-b", self.queue, self.registry, self.now)
        self.assertEqual(second["idempotency_key"], "low")
        self.assertIsNone(claim_next("worker-c", self.queue, self.registry, self.now))

    def test_success_requires_matching_live_lease(self):
        self.enqueue()
        claimed = claim_next("worker-a", self.queue, self.registry, self.now)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            complete_task(claimed["task_id"], "worker-b", claimed["lease"]["token"],
                          success=True, result={"ok": True}, queue_path=self.queue,
                          registry_path=self.registry, now=self.now)
        done = complete_task(claimed["task_id"], "worker-a", claimed["lease"]["token"],
                             success=True, result={"ok": True}, queue_path=self.queue,
                             registry_path=self.registry, now=self.now)
        self.assertEqual(done["status"], "SUCCEEDED")
        self.assertEqual(done["state_history"], ["QUEUED", "CLAIMED", "SUCCEEDED"])

    def test_failed_attempt_is_requeued_with_backoff(self):
        self.enqueue()
        claimed = claim_next("worker-a", self.queue, self.registry, self.now)
        failed = complete_task(claimed["task_id"], "worker-a", claimed["lease"]["token"],
                               success=False, error={"type": "temporary"}, queue_path=self.queue,
                               registry_path=self.registry, now=self.now)
        self.assertEqual(failed["status"], "QUEUED")
        self.assertEqual(failed["state_history"], ["QUEUED", "CLAIMED", "FAILED", "QUEUED"])
        self.assertEqual(datetime.fromisoformat(failed["not_before"].replace("Z", "+00:00")),
                         self.now + timedelta(seconds=30))

    def test_exhausted_attempts_go_to_dead_letter(self):
        self.enqueue()
        first = claim_next("worker-a", self.queue, self.registry, self.now)
        retry = complete_task(first["task_id"], "worker-a", first["lease"]["token"],
                              success=False, error={"type": "temporary"}, queue_path=self.queue,
                              registry_path=self.registry, now=self.now)
        second_now = self.now + timedelta(seconds=31)
        second = claim_next("worker-b", self.queue, self.registry, second_now)
        final = complete_task(second["task_id"], "worker-b", second["lease"]["token"],
                              success=False, error={"type": "still_failing"}, queue_path=self.queue,
                              registry_path=self.registry, now=second_now)
        self.assertEqual(retry["status"], "QUEUED")
        self.assertEqual(final["status"], "DEAD_LETTER")
        self.assertEqual(final["attempts"], 2)

    def test_expired_lease_is_recovered(self):
        self.enqueue()
        claimed = claim_next("worker-a", self.queue, self.registry, self.now)
        after_expiry = self.now + timedelta(seconds=121)
        recovered = recover_expired(self.queue, self.registry, after_expiry)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["task_id"], claimed["task_id"])
        self.assertEqual(recovered[0]["status"], "QUEUED")
        self.assertIsNone(recovered[0]["lease"])

    def test_expired_final_attempt_goes_to_dead_letter(self):
        self.enqueue()
        first = claim_next("worker-a", self.queue, self.registry, self.now)
        retry = complete_task(first["task_id"], "worker-a", first["lease"]["token"],
                              success=False, error={"type": "temporary"}, queue_path=self.queue,
                              registry_path=self.registry, now=self.now)
        second_now = self.now + timedelta(seconds=31)
        second = claim_next("worker-b", self.queue, self.registry, second_now)
        recovered = recover_expired(self.queue, self.registry, second_now + timedelta(seconds=121))
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["task_id"], second["task_id"])
        self.assertEqual(recovered[0]["status"], "DEAD_LETTER")

    def test_idempotency_key_cannot_be_reused_for_different_payload(self):
        self.enqueue(input={"value": 1})
        with self.assertRaisesRegex(ValueError, "different task payload"):
            self.enqueue(input={"value": 2})

    def test_runtime_outputs_pass_queue_integrity_validator(self):
        self.enqueue()
        claimed = claim_next("worker-a", self.queue, self.registry, self.now)
        complete_task(claimed["task_id"], "worker-a", claimed["lease"]["token"],
                      success=True, result={"ok": True}, queue_path=self.queue,
                      registry_path=self.registry, now=self.now)
        result = validate_task_queue(self.root, self.queue, self.registry)
        self.assertTrue(result["valid"])
        self.assertEqual(result["task_count"], 1)

    def test_expired_lease_cannot_be_completed(self):
        self.enqueue()
        claimed = claim_next("worker-a", self.queue, self.registry, self.now)
        with self.assertRaisesRegex(ValueError, "lease has expired"):
            complete_task(claimed["task_id"], "worker-a", claimed["lease"]["token"],
                          success=True, result={"ok": True}, queue_path=self.queue,
                          registry_path=self.registry, now=self.now + timedelta(seconds=121))



    def test_local_queue_consumes_manual_authorization_once_for_exact_task(self):
        idem = "production:manual-authorized:fp:123"
        task = {
            "idempotency_key": idem,
            "requester_program_id": "workflow_automation_watchdog",
            "target_program_id": "workflow_auto_sync",
            "capability": "deterministic_audit",
            "input": {
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
        }
        env = {
            "GITHUB_REPOSITORY": "instarrys-bit/default",
            "GITHUB_WORKFLOW_REF": "instarrys-bit/default/.github/workflows/automation-watchdog.yml@refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_ACTOR": "maintainer",
            "GITHUB_ACTOR_ID": "678", "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1", "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40, "GITHUB_MANUAL_AUDIT_REQUEST": "true",
        }
        with patch.dict("os.environ", env, clear=True):
            first = enqueue_task(task, self.queue, self.registry, self.now)
            replay = enqueue_task(task, self.queue, self.registry, self.now)
            self.assertTrue(first["created"])
            self.assertFalse(replay["created"])
            record = json.loads(self.queue.read_text(encoding="utf-8"))["manual_authorizations"]["123"]
            self.assertEqual(record["task_id"], first["task"]["task_id"])
            with self.assertRaisesRegex(ValueError, "already been consumed"):
                second = dict(task)
                second["idempotency_key"] = idem + ":second"
                second["input"] = dict(task["input"], authorization_idempotency_key=idem + ":second")
                enqueue_task(second, self.queue, self.registry, self.now)

if __name__ == "__main__":
    unittest.main()
