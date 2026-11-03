import copy
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import task_scheduler
import task_result_verifier
from remote_task_queue_runtime import enqueue_remote
from task_result_verifier import verify_pending_remote


class MemoryStore:
    def __init__(self):
        self.document = {"schema_version": 1, "revision": 0, "tasks": []}
        self.repository = "owner/repo"
        self.branch = "main"
        self.token = "fake-token"

    def read(self):
        return type("Snapshot", (), {"document": copy.deepcopy(self.document), "content_sha": "fake-sha"})()

    def mutate(self, mutator, max_conflicts=5):
        candidate, result = mutator(copy.deepcopy(self.document))
        if candidate != self.document:
            self.document = candidate
        return result


class FakeWorkflowClient:
    def __init__(self, repository, token=None, timeout=15):
        self.repository = repository
        self.token = token
        self.timeout = timeout
        self.dispatches = []
        self.runs = []
        self.run_details = {}
        self.workflow = {
            "id": 1234,
            "path": ".github/workflows/workflow-target.yml",
            "state": "active",
        }
        self.ref = {"object": {"sha": "a" * 40}}

    def get_workflow(self, path):
        return self.workflow

    def get_ref(self, ref):
        return self.ref

    def dispatch(self, workflow_id, ref, inputs):
        self.dispatches.append((workflow_id, ref, inputs))
        return None

    def list_runs(self, workflow_id, ref):
        return {"workflow_runs": self.runs}

    def get_run(self, run_id):
        return self.run_details[run_id]

    def add_run(self, task_id, attempt=1, status="in_progress", conclusion=None):
        correlation = f"{task_id}-a{attempt}"
        row = {
            "id": 991,
            "workflow_id": 1234,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": "a" * 40,
            "display_title": f"Automation task {correlation}",
            "status": status,
            "conclusion": conclusion,
            "html_url": "https://example.invalid/actions/runs/991",
        }
        self.runs = [row]
        self.run_details[991] = row
        return row


class WorkflowSchedulerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "scripts").mkdir()
        (self.root / "shadowrocket").mkdir()
        (self.root / "shadowrocket" / "ss.conf").write_text("[General]\n", encoding="utf-8")
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "workflow-target.yml").write_text(
            "run-name: Automation task \${{ inputs.automation_task_id || 'manual' }}\n"
            "on:\n  workflow_dispatch:\n    inputs:\n"
            "      domains:\n        required: true\n        type: string\n"
            "      automation_task_id:\n        required: false\n        type: string\n",
            encoding="utf-8",
        )
        self.registry = {"programs": [
            {"id": "script_requester", "path": "scripts/requester.py",
             "kind": "python_component", "capabilities": ["request"],
             "orchestration": {"enabled": False, "allowed_callers": [],
                               "max_attempts": 0, "timeout_seconds": 300}},
            {"id": "workflow_target", "path": ".github/workflows/workflow-target.yml",
             "kind": "github_actions_workflow", "capabilities": ["workflow_capability"],
             "orchestration": {"enabled": True, "allowed_callers": ["script_requester"],
                               "max_attempts": 2, "timeout_seconds": 300}},
            {"id": "script_task_result_verifier", "path": "scripts/task_result_verifier.py",
             "kind": "python_component", "capabilities": ["task_result_verification"],
             "orchestration": {"enabled": False, "allowed_callers": [],
                               "max_attempts": 0, "timeout_seconds": 300}},
        ]}
        self.adapter = {
            "target_program_id": "workflow_target",
            "target_kind": "github_actions_workflow",
            "adapter_type": "github_actions_workflow",
            "enabled": True,
            "interface_status": "workflow_dispatch_reviewed",
            "allowed_callers": ["script_requester"],
            "workflow": {
                "path": ".github/workflows/workflow-target.yml",
                "dispatchable": True,
                "inputs": [
                    {"name": "domains", "type": "string", "required": True},
                    {"name": "automation_task_id", "type": "string", "required": False},
                ],
                "allowed_refs": ["main"],
                "caller_permissions_required": ["actions:write"],
            },
            "timeout_seconds": 30,
            "retry": {"max_attempts": 2},
            "completion": {"independent_verification_required": True},
        }
        self.adapters = {"schema_version": 1, "adapters": [self.adapter]}
        self.store = MemoryStore()
        self.now = datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc)
        self.client = FakeWorkflowClient("owner/repo")

    def enqueue(self):
        return enqueue_remote({
            "idempotency_key": "workflow:test:once",
            "requester_program_id": "script_requester",
            "target_program_id": "workflow_target",
            "capability": "workflow_capability",
            "input": {"domains": "example.com"},
        }, self.store, self.registry, self.now)["task"]

    def test_watchdog_can_enqueue_production_audit_idempotently(self):
        registry = {"programs": [
            {"id": "workflow_automation_watchdog", "path": ".github/workflows/automation-watchdog.yml",
             "kind": "github_actions_workflow", "capabilities": ["top_level_supervision"],
             "orchestration": {"enabled": False, "allowed_callers": [], "max_attempts": 0, "timeout_seconds": 300}},
            {"id": "workflow_auto_sync", "path": ".github/workflows/workflow-target.yml",
             "kind": "github_actions_workflow", "capabilities": ["deterministic_audit"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 1, "timeout_seconds": 300}},
        ]}
        store = MemoryStore()
        key = "auto-sync-stale:" + "a" * 40
        origin = {
            "baseline_source_event": "push",
            "baseline_source_actor": "instarrys-bit",
            "baseline_source_before": "b" * 40,
            "baseline_source_sha": "a" * 40,
        }
        first = task_scheduler.enqueue_auto_sync_task(
            store, registry, idempotency_key=key, priority=90, input_payload=origin,
        )
        second = task_scheduler.enqueue_auto_sync_task(
            store, registry, idempotency_key=key, priority=90, input_payload=origin,
        )
        saved = store.document["tasks"][0]
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertEqual(saved["requester_program_id"], "workflow_automation_watchdog")
        self.assertEqual(saved["target_program_id"], "workflow_auto_sync")
        self.assertEqual(saved["capability"], "deterministic_audit")
        self.assertEqual(saved["input"], origin)
        self.assertEqual(saved["status"], "QUEUED")

    def test_watchdog_baseline_sha_survives_durable_queue_and_workflow_dispatch(self):
        registry = {"programs": [
            {"id": "workflow_automation_watchdog", "path": ".github/workflows/automation-watchdog.yml",
             "kind": "github_actions_workflow", "capabilities": ["top_level_supervision"],
             "orchestration": {"enabled": False, "allowed_callers": [], "max_attempts": 0, "timeout_seconds": 300}},
            {"id": "workflow_auto_sync", "path": ".github/workflows/workflow-target.yml",
             "kind": "github_actions_workflow", "capabilities": ["deterministic_audit"],
             "orchestration": {"enabled": True, "allowed_callers": ["workflow_automation_watchdog"],
                               "max_attempts": 1, "timeout_seconds": 300}},
        ]}
        workflow_path = self.root / ".github" / "workflows" / "workflow-target.yml"
        workflow_path.write_text(
            "on:\\n  workflow_dispatch:\\n    inputs:\\n"
            "      domains:\\n        required: true\\n        type: string\\n"
            "      baseline_source_sha:\\n        required: false\\n        type: string\\n"
            "      production_fingerprint:\\n        required: false\\n        type: string\\n"
            "      production_decision:\\n        required: false\\n        type: string\\n"
            "      production_reason:\\n        required: false\\n        type: string\\n"
            "      automation_task_id:\\n        required: false\\n        type: string\\n",
            encoding="utf-8",
        )
        adapter = copy.deepcopy(self.adapter)
        adapter["target_program_id"] = "workflow_auto_sync"
        adapter["allowed_callers"] = ["workflow_automation_watchdog"]
        adapter["workflow"]["inputs"].extend([
            {"name": "baseline_source_sha", "type": "string", "required": False},
            {"name": "production_fingerprint", "type": "string", "required": False},
            {"name": "production_decision", "type": "string", "required": False},
            {"name": "production_reason", "type": "string", "required": False},
        ])
        adapters = {"schema_version": 1, "adapters": [adapter]}
        origin = {
            "domains": "example.com",
            "baseline_source_event": "push",
            "baseline_source_actor": "repository-owner",
            "baseline_source_before": "b" * 40,
            "baseline_source_sha": "a" * 40,
            "production_fingerprint": "f" * 64,
            "production_decision": "INPUT_CHANGED",
            "production_reason": "shadowrocket/ss.conf changed",
        }
        task_scheduler.enqueue_auto_sync_task(
            self.store, registry, idempotency_key="config-baseline:" + "a" * 40,
            priority=100, input_payload=origin,
        )
        with patch.object(task_scheduler, "GitHubWorkflowClient", return_value=self.client):
            report = task_scheduler.run_scheduler_once(
                self.store, registry, adapters,
                worker_id="watchdog-config-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.assertEqual(report["processed_count"], 1)
        dispatched = self.client.dispatches[0][2]
        for field in (
            "baseline_source_sha", "production_fingerprint",
            "production_decision", "production_reason",
        ):
            self.assertEqual(dispatched[field], origin[field])
        self.assertEqual(
            self.store.document["tasks"][0]["input"]["baseline_source_sha"],
            "a" * 40,
        )

    def test_scheduler_dispatches_once_and_leaves_task_verifying(self):
        task = self.enqueue()
        with patch.object(task_scheduler, "GitHubWorkflowClient", return_value=self.client):
            report = task_scheduler.run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="workflow-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.assertEqual(report["processed_count"], 1)
        self.assertEqual(len(self.client.dispatches), 1)
        saved = self.store.document["tasks"][0]
        self.assertEqual(saved["status"], "VERIFYING")
        self.assertEqual(saved["dispatch_intent"]["dispatch_attempt"], 1)
        self.assertEqual(saved["result"]["dispatch_state"], "submitted")
        self.assertEqual(
            self.client.dispatches[0][2]["automation_task_id"],
            task["task_id"] + "-a1",
        )

    def test_independent_verifier_waits_then_accepts_only_completed_success(self):
        task = self.enqueue()
        with patch.object(task_scheduler, "GitHubWorkflowClient", return_value=self.client):
            task_scheduler.run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="workflow-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.client.add_run(task["task_id"], status="in_progress")
        pending = verify_pending_remote(
            self.store, self.registry, self.adapters, self.now, workflow_client=self.client,
        )
        self.assertEqual(pending["verified"], [])
        self.assertEqual(self.store.document["tasks"][0]["status"], "VERIFYING")
        self.client.add_run(task["task_id"], status="completed", conclusion="success")
        verified = verify_pending_remote(
            self.store, self.registry, self.adapters, self.now, workflow_client=self.client,
        )
        saved = self.store.document["tasks"][0]
        self.assertEqual(verified["verified"], [task["task_id"]])
        self.assertEqual(saved["status"], "SUCCEEDED")
        self.assertEqual(saved["verification"]["status"], "passed")
        self.assertEqual(saved["result"]["run_evidence"]["run_id"], 991)

    def test_unknown_dispatch_outcome_is_reconciled_without_redispatch(self):
        task = self.enqueue()
        def uncertain(*args, **kwargs):
            from github_workflow_adapter import WorkflowDispatchOutcomeUnknown
            raise WorkflowDispatchOutcomeUnknown("network response lost")
        self.client.dispatch = uncertain
        with patch.object(task_scheduler, "GitHubWorkflowClient", return_value=self.client):
            task_scheduler.run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="workflow-test", max_tasks=1, root=self.root, now=self.now,
            )
        saved = self.store.document["tasks"][0]
        self.assertEqual(saved["status"], "VERIFYING")
        self.assertEqual(saved["result"]["dispatch_state"], "unknown")
        self.assertEqual(len(self.client.dispatches), 0)
        self.client.add_run(task["task_id"], status="completed", conclusion="success")
        verified = verify_pending_remote(
            self.store, self.registry, self.adapters, self.now, workflow_client=self.client,
        )
        self.assertEqual(verified["verified"], [task["task_id"]])

    def test_recovered_intent_is_reconciled_not_redispatched(self):
        task = self.enqueue()
        task["attempts"] = 1
        task["dispatch_intent"] = {
            "workflow_id": 1234,
            "workflow_path": ".github/workflows/workflow-target.yml",
            "ref": "main",
            "requested_head_sha": "a" * 40,
            "task_id": task["task_id"],
            "dispatch_attempt": 1,
            "correlation_id": task["task_id"] + "-a1",
            "correlation_title": "Automation task " + task["task_id"] + "-a1",
            "prepared_at": "2026-11-03T04:00:00Z",
        }
        self.client.add_run(task["task_id"], status="in_progress")
        with patch.object(task_scheduler, "GitHubWorkflowClient", return_value=self.client), \
             patch.object(task_result_verifier, "GitHubWorkflowClient", return_value=self.client):
            report = task_scheduler.run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="workflow-test", max_tasks=1, root=self.root, now=self.now,
            )
        saved = self.store.document["tasks"][0]
        self.assertEqual(report["processed_count"], 0)
        self.assertEqual(saved["status"], "VERIFYING")
        self.assertEqual(saved["result"]["run_evidence"]["run_id"], 991)
        self.assertEqual(len(self.client.dispatches), 0)

    def test_dead_letter_with_unresolved_intent_can_only_recover_via_verified_run(self):
        task = self.enqueue()
        task["attempts"] = 2
        task["state_history"] = ["QUEUED", "CLAIMED", "DEAD_LETTER"]
        task["status"] = "DEAD_LETTER"
        task["dispatch_intent"] = {
            "workflow_id": 1234,
            "workflow_path": ".github/workflows/workflow-target.yml",
            "ref": "main",
            "requested_head_sha": "a" * 40,
            "task_id": task["task_id"],
            "dispatch_attempt": 2,
            "correlation_id": task["task_id"] + "-a2",
            "correlation_title": "Automation task " + task["task_id"] + "-a2",
            "prepared_at": "2026-11-03T04:00:00Z",
        }
        self.client.add_run(task["task_id"], attempt=2, status="completed", conclusion="success")
        report = verify_pending_remote(
            self.store, self.registry, self.adapters, self.now, workflow_client=self.client,
        )
        saved = self.store.document["tasks"][0]
        self.assertEqual(report["verified"], [task["task_id"]])
        self.assertEqual(saved["status"], "SUCCEEDED")
        self.assertEqual(saved["state_history"][-2:], ["VERIFYING", "SUCCEEDED"])

    def test_completed_failure_retries_with_new_attempt_correlation(self):
        task = self.enqueue()
        with patch.object(task_scheduler, "GitHubWorkflowClient", return_value=self.client):
            task_scheduler.run_scheduler_once(
                self.store, self.registry, self.adapters,
                worker_id="workflow-test", max_tasks=1, root=self.root, now=self.now,
            )
        self.client.add_run(task["task_id"], status="completed", conclusion="failure")
        report = verify_pending_remote(
            self.store, self.registry, self.adapters, self.now, workflow_client=self.client,
        )
        saved = self.store.document["tasks"][0]
        self.assertEqual(report["rejected"], [task["task_id"]])
        self.assertEqual(saved["status"], "QUEUED")
        self.assertNotIn("dispatch_intent", saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
