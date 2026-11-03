import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from github_workflow_adapter import (
    AmbiguousWorkflowRun, WorkflowAPIError, find_correlated_run,
    inspect_correlated_run, prepare_dispatch, submit_dispatch,
    validate_dispatch_request,
)


class FakeGitHub:
    def __init__(self):
        self.dispatched = []
        self.runs = []
        self.run_detail = {}
        self.workflow = {"id": 1234, "path": ".github/workflows/request-intake.yml", "state": "active"}
        self.ref = {"object": {"sha": "a" * 40}}

    def get_workflow(self, path):
        self.requested_workflow_path = path
        return self.workflow

    def get_ref(self, ref):
        self.requested_ref = ref
        return self.ref

    def dispatch(self, workflow_id, ref, inputs):
        self.dispatched.append((workflow_id, ref, inputs))
        return None

    def list_runs(self, workflow_id, ref):
        self.list_request = (workflow_id, ref)
        return {"workflow_runs": self.runs}

    def get_run(self, run_id):
        return self.run_detail[run_id]


class WorkflowAdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeGitHub()
        self.adapter = {
            "adapter_type": "github_actions_workflow",
            "enabled": True,
            "interface_status": "workflow_dispatch_reviewed",
            "allowed_callers": ["workflow_automation_watchdog"],
            "workflow": {
                "path": ".github/workflows/request-intake.yml",
                "dispatchable": True,
                "allowed_refs": ["main"],
                "inputs": [
                    {"name": "domains", "type": "string", "required": True},
                    {"name": "automation_task_id", "type": "string", "required": False},
                ],
            },
        }
        self.task = {
            "task_id": "task_0123456789abcdef01234567",
            "requester_program_id": "workflow_automation_watchdog",
            "input": {"domains": "example.com"},
        }

    def prepare(self):
        return prepare_dispatch(self.client, self.adapter, self.task, now=None)

    def test_validates_and_injects_reserved_correlation_input(self):
        inputs = validate_dispatch_request(self.adapter, self.task, "main")
        self.assertEqual(inputs, {
            "domains": "example.com",
            "automation_task_id": self.task["task_id"],
        })

    def test_rejects_disabled_adapter_unapproved_caller_and_ref(self):
        disabled = dict(self.adapter, enabled=False)
        with self.assertRaisesRegex(ValueError, "disabled"):
            validate_dispatch_request(disabled, self.task, "main")
        unauthorized = dict(self.task, requester_program_id="workflow_request_intake")
        with self.assertRaisesRegex(ValueError, "caller allowlist"):
            validate_dispatch_request(self.adapter, unauthorized, "main")
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            validate_dispatch_request(self.adapter, self.task, "feature")

    def test_rejects_missing_required_unknown_and_reserved_inputs(self):
        with self.assertRaisesRegex(ValueError, "required workflow input"):
            validate_dispatch_request(self.adapter, dict(self.task, input={}), "main")
        with self.assertRaisesRegex(ValueError, "unsupported workflow input"):
            validate_dispatch_request(self.adapter, dict(self.task, input={"domains": "x", "extra": "y"}), "main")
        with self.assertRaisesRegex(ValueError, "reserved"):
            validate_dispatch_request(
                self.adapter,
                dict(self.task, input={"domains": "x", "automation_task_id": "forged"}),
                "main",
            )
        with self.assertRaisesRegex(ValueError, "must be a string"):
            validate_dispatch_request(self.adapter, dict(self.task, input={"domains": 123}), "main")

    def test_prepare_checks_live_workflow_identity_and_ref_sha(self):
        intent = self.prepare()
        self.assertEqual(intent["workflow_id"], 1234)
        self.assertEqual(intent["requested_head_sha"], "a" * 40)
        self.assertEqual(intent["correlation_title"], "Automation task " + self.task["task_id"])
        self.client.workflow["state"] = "disabled_manually"
        with self.assertRaisesRegex(WorkflowAPIError, "identity or active state"):
            self.prepare()

    def test_submit_dispatch_sends_only_reviewed_inputs(self):
        intent = self.prepare()
        result = submit_dispatch(self.client, intent)
        self.assertEqual(self.client.dispatched, [(
            1234, "main",
            {"domains": "example.com", "automation_task_id": self.task["task_id"]},
        )])
        self.assertEqual(result["dispatch_state"], "submitted")
        self.assertEqual(result["task_id"], self.task["task_id"])
        self.assertNotIn("inputs", result)

    def test_find_run_requires_exact_correlation_and_rejects_ambiguity(self):
        intent = self.prepare()
        matching = {
            "id": 88, "workflow_id": 1234, "event": "workflow_dispatch",
            "head_branch": "main", "head_sha": "a" * 40,
            "display_title": intent["correlation_title"], "status": "queued",
        }
        self.client.runs = [
            dict(matching, id=87, display_title="Automation task another"),
            matching,
        ]
        self.assertEqual(find_correlated_run(self.client, intent), matching)
        self.client.runs.append(dict(matching, id=89))
        with self.assertRaises(AmbiguousWorkflowRun):
            find_correlated_run(self.client, intent)

    def test_inspection_does_not_assume_dispatch_acceptance_means_success(self):
        intent = self.prepare()
        self.assertEqual(inspect_correlated_run(self.client, intent)["state"], "pending")
        listed = {
            "id": 88, "workflow_id": 1234, "event": "workflow_dispatch",
            "head_branch": "main", "head_sha": "a" * 40,
            "display_title": intent["correlation_title"],
        }
        self.client.runs = [listed]
        self.client.run_detail[88] = dict(listed, status="in_progress", conclusion=None, html_url="https://example.invalid/run/88")
        self.assertEqual(inspect_correlated_run(self.client, intent)["state"], "pending")
        self.client.run_detail[88] = dict(listed, status="completed", conclusion="success", html_url="https://example.invalid/run/88")
        result = inspect_correlated_run(self.client, intent)
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["evidence"]["run_id"], 88)

    def test_failed_run_is_not_success_and_identity_mismatch_fails_closed(self):
        intent = self.prepare()
        listed = {
            "id": 88, "workflow_id": 1234, "event": "workflow_dispatch",
            "head_branch": "main", "head_sha": "a" * 40,
            "display_title": intent["correlation_title"],
        }
        self.client.runs = [listed]
        self.client.run_detail[88] = dict(listed, status="completed", conclusion="failure")
        self.assertEqual(inspect_correlated_run(self.client, intent)["state"], "failure")
        self.client.run_detail[88] = dict(listed, status="completed", conclusion="success", head_sha="b" * 40)
        with self.assertRaisesRegex(WorkflowAPIError, "identity"):
            inspect_correlated_run(self.client, intent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
