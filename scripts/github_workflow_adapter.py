#!/usr/bin/env python3
"""GitHub Actions workflow dispatch and run-correlation primitives.

Production use is gated by the scheduler's reviewed adapter, caller allowlist,
allowlisted ref, persisted dispatch intent, and independent run verifier.
"""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()


import argparse
import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class WorkflowAPIError(RuntimeError):
    """GitHub rejected a workflow adapter request."""


class WorkflowDispatchOutcomeUnknown(WorkflowAPIError):
    """The dispatch request may have reached GitHub, but no response was received."""


class WorkflowDispatchRejected(WorkflowAPIError):
    """GitHub explicitly rejected a dispatch request; retry may be safe."""


class AmbiguousWorkflowRun(WorkflowAPIError):
    """More than one run matches a task correlation marker."""


def utc_stamp(value: datetime | None = None) -> str:
    value = value or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class GitHubWorkflowClient:
    """Small GitHub Actions REST client with sanitized failures."""

    def __init__(self, repository: str, token: str | None = None,
                 api_url: str = "https://api.github.com", timeout: int = 15):
        if not isinstance(repository, str) or repository.count("/") != 1:
            raise ValueError("repository must be owner/name")
        self.repository = repository
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict | None = None):
        if not self.token:
            raise WorkflowAPIError("GitHub token is required; token value was not logged")
        url = f"{self.api_url}/repos/{self.repository}/{path.lstrip('/')}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "shadowrocket-automation-workflow-adapter",
        }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
                if not raw:
                    return None
        except HTTPError as exc:
            if method == "POST" and path.endswith("/dispatches"):
                if 400 <= exc.code < 500:
                    raise WorkflowDispatchRejected(f"GitHub rejected workflow dispatch with HTTP {exc.code}") from None
                raise WorkflowDispatchOutcomeUnknown(
                    f"GitHub dispatch endpoint returned HTTP {exc.code}; reconcile by task correlation before retrying"
                ) from None
            raise WorkflowAPIError(f"GitHub Actions API returned HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError):
            if method == "POST" and path.endswith("/dispatches"):
                raise WorkflowDispatchOutcomeUnknown(
                    "workflow dispatch response was not received; reconcile by task correlation before retrying"
                ) from None
            raise WorkflowAPIError("GitHub Actions API request failed or timed out") from None
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WorkflowAPIError("GitHub Actions API returned invalid JSON") from None
        if not isinstance(value, dict):
            raise WorkflowAPIError("GitHub Actions API response must be an object")
        return value

    def get_workflow(self, workflow_path: str) -> dict:
        filename = workflow_path.rsplit("/", 1)[-1]
        return self.request("GET", f"actions/workflows/{quote(filename, safe='')}")

    def get_ref(self, ref: str) -> dict:
        encoded = quote(ref, safe="/")
        return self.request("GET", f"git/ref/heads/{encoded}")

    def dispatch(self, workflow_id: int, ref: str, inputs: dict):
        return self.request(
            "POST", f"actions/workflows/{workflow_id}/dispatches",
            {"ref": ref, "inputs": inputs},
        )

    def list_runs(self, workflow_id: int, ref: str) -> dict:
        query = urlencode({"event": "workflow_dispatch", "branch": ref, "per_page": 100})
        return self.request("GET", f"actions/workflows/{workflow_id}/runs?{query}")

    def get_run(self, run_id: int) -> dict:
        return self.request("GET", f"actions/runs/{run_id}")

    def get_commit(self, commit_sha: str) -> dict:
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise WorkflowAPIError("workflow run commit SHA is invalid")
        return self.request("GET", f"commits/{commit_sha}")


def validate_dispatch_request(adapter: dict, task: dict, ref: str) -> dict:
    """Validate exact caller, input names/types, and allowed ref before API access."""
    if adapter.get("adapter_type") != "github_actions_workflow":
        raise ValueError("target is not a GitHub Actions workflow adapter")
    if adapter.get("enabled") is not True:
        raise ValueError("workflow adapter is disabled")
    if adapter.get("interface_status") != "workflow_dispatch_reviewed":
        raise ValueError("workflow dispatch interface is not reviewed")
    workflow = adapter.get("workflow")
    if not isinstance(workflow, dict) or workflow.get("dispatchable") is not True:
        raise ValueError("workflow is not dispatchable")
    if ref not in workflow.get("allowed_refs", []):
        raise ValueError("requested ref is not allowlisted")
    callers = adapter.get("allowed_callers", [])
    if task.get("requester_program_id") not in callers:
        raise ValueError("requester is not in the workflow adapter caller allowlist")
    task_id = task.get("task_id")
    attempt = task.get("attempts")
    if not isinstance(task_id, str) or not task_id.startswith("task_"):
        raise ValueError("task_id is required for workflow run correlation")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise ValueError("task attempt number is invalid for workflow run correlation")
    correlation_attempt = max(1, attempt)
    supplied = task.get("input")
    if not isinstance(supplied, dict):
        raise ValueError("workflow task input must be an object")
    declared = workflow.get("inputs")
    if not isinstance(declared, list):
        raise ValueError("workflow input contract is missing")
    by_name = {item.get("name"): item for item in declared if isinstance(item, dict)}
    if len(by_name) != len(declared) or "automation_task_id" not in by_name:
        raise ValueError("workflow must declare a unique automation_task_id correlation input")
    if "automation_task_id" in supplied:
        raise ValueError("automation_task_id is reserved and cannot be supplied by the caller")
    unknown = sorted(set(supplied) - set(by_name))
    if unknown:
        raise ValueError("unsupported workflow input(s): " + ", ".join(unknown))
    inputs = dict(supplied)
    inputs["automation_task_id"] = f"{task_id}-a{correlation_attempt}"
    for name, spec in by_name.items():
        value = inputs.get(name)
        if value is None:
            if spec.get("required") is True:
                raise ValueError(f"required workflow input is missing: {name}")
            continue
        kind = spec.get("type")
        if kind == "string" and not isinstance(value, str):
            raise ValueError(f"workflow input {name} must be a string")
        if kind == "boolean" and not isinstance(value, bool):
            raise ValueError(f"workflow input {name} must be a boolean")
        if kind not in {"string", "boolean"}:
            raise ValueError(f"unsupported workflow input type for {name}: {kind}")
    return inputs


def prepare_dispatch(client: GitHubWorkflowClient, adapter: dict, task: dict,
                     ref: str = "main", now: datetime | None = None) -> dict:
    """Read immutable workflow/ref identity and create a correlation intent."""
    inputs = validate_dispatch_request(adapter, task, ref)
    workflow_path = adapter["workflow"]["path"]
    metadata = client.get_workflow(workflow_path)
    workflow_id = metadata.get("id")
    if (metadata.get("path") != workflow_path or metadata.get("state") != "active"
            or isinstance(workflow_id, bool) or not isinstance(workflow_id, int)):
        raise WorkflowAPIError("GitHub workflow identity or active state does not match the reviewed adapter")
    ref_data = client.get_ref(ref)
    commit_sha = ((ref_data.get("object") or {}).get("sha")
                  if isinstance(ref_data.get("object"), dict) else None)
    if not isinstance(commit_sha, str) or len(commit_sha) != 40:
        raise WorkflowAPIError("GitHub ref did not resolve to a commit SHA")
    task_id = task["task_id"]
    correlation_id = inputs["automation_task_id"]
    return {
        "workflow_id": workflow_id,
        "workflow_path": workflow_path,
        "ref": ref,
        "requested_head_sha": commit_sha,
        "task_id": task_id,
        "dispatch_attempt": task["attempts"],
        "correlation_id": correlation_id,
        "correlation_title": f"Automation task {correlation_id}",
        "inputs": inputs,
        "prepared_at": utc_stamp(now),
    }


def submit_dispatch(client: GitHubWorkflowClient, intent: dict) -> dict:
    """Submit exactly one dispatch request; callers must persist intent first."""
    response = client.dispatch(intent["workflow_id"], intent["ref"], intent["inputs"])
    if response is not None:
        raise WorkflowDispatchOutcomeUnknown("workflow dispatch returned an unexpected response body; reconcile by task correlation before retrying")
    return {
        key: intent[key] for key in (
            "workflow_id", "workflow_path", "ref", "requested_head_sha",
            "task_id", "dispatch_attempt", "correlation_id", "correlation_title", "prepared_at",
        )
    } | {"dispatch_state": "submitted", "submitted_at": utc_stamp()}


def validate_run_head_sha(client: GitHubWorkflowClient, intent: dict, actual_sha: str) -> str:
    """Allow exact ref identity or the one queue-only commit created while persisting dispatch intent."""
    expected_sha = intent.get("requested_head_sha")
    if actual_sha == expected_sha:
        return "exact"
    if not isinstance(actual_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", actual_sha):
        raise WorkflowAPIError("correlated workflow run commit SHA is invalid")
    commit = client.get_commit(actual_sha)
    parents = commit.get("parents")
    files = commit.get("files")
    message = (commit.get("commit") or {}).get("message") if isinstance(commit.get("commit"), dict) else None
    if (
        not isinstance(parents, list)
        or len(parents) != 1
        or not isinstance(parents[0], dict)
        or parents[0].get("sha") != expected_sha
        or not isinstance(files, list)
        or len(files) != 1
        or not isinstance(files[0], dict)
        or files[0].get("filename") != "automation/task_queue.json"
        or files[0].get("status") != "modified"
        or message != "Update durable automation task queue"
    ):
        raise WorkflowAPIError(
            "correlated workflow run does not match the persisted workflow/ref/SHA identity; "
            "only the exact single-parent queue-intent commit is permitted"
        )
    return "queue_intent_commit_only"


def find_correlated_run(client: GitHubWorkflowClient, intent: dict) -> dict | None:
    """Find exactly one run by workflow ID, ref, SHA, event, and unique run-name."""
    payload = client.list_runs(intent["workflow_id"], intent["ref"])
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise WorkflowAPIError("workflow runs response is missing workflow_runs")
    matches = [
        run for run in runs
        if isinstance(run, dict) and run.get("display_title") == intent["correlation_title"]
    ]
    if len(matches) > 1:
        raise AmbiguousWorkflowRun("multiple workflow runs match one task correlation ID")
    if not matches:
        return None
    run = matches[0]
    expected = {
        "workflow_id": intent["workflow_id"],
        "event": "workflow_dispatch",
        "head_branch": intent["ref"],
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise WorkflowAPIError("correlated workflow run does not match the persisted workflow/ref identity")
    validate_run_head_sha(client, intent, run.get("head_sha"))
    return run


def inspect_correlated_run(client: GitHubWorkflowClient, intent: dict) -> dict:
    """Independently inspect the exact run; never infer success from dispatch acceptance."""
    listed = find_correlated_run(client, intent)
    if listed is None:
        return {"state": "pending", "reason": "correlated workflow run is not visible yet"}
    run_id = listed.get("id")
    if isinstance(run_id, bool) or not isinstance(run_id, int):
        raise WorkflowAPIError("correlated workflow run has no valid run ID")
    run = client.get_run(run_id)
    required = {
        "workflow_id": intent["workflow_id"],
        "event": "workflow_dispatch",
        "head_branch": intent["ref"],
        "display_title": intent["correlation_title"],
    }
    if any(run.get(key) != value for key, value in required.items()):
        raise WorkflowAPIError("workflow run identity does not match the persisted dispatch intent")
    if run.get("head_sha") != listed.get("head_sha"):
        raise WorkflowAPIError("workflow run identity commit SHA changed between list and detail reads")
    head_sha_relationship = validate_run_head_sha(client, intent, run.get("head_sha"))
    if run.get("status") != "completed":
        return {"state": "pending", "run_id": run_id, "html_url": run.get("html_url"), "run_status": run.get("status")}
    conclusion = run.get("conclusion")
    evidence = {
        "run_id": run_id,
        "html_url": run.get("html_url"),
        "head_sha": run.get("head_sha"),
        "requested_head_sha": intent["requested_head_sha"],
        "head_sha_relationship": head_sha_relationship,
        "status": run.get("status"),
        "conclusion": conclusion,
    }
    if conclusion == "success":
        return {"state": "success", "evidence": evidence}
    return {
        "state": "failure",
        "evidence": evidence,
        "reason": f"workflow completed with conclusion {conclusion!r}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--help-contract", action="store_true",
                        help="print the supported workflow-dispatch contract")
    args = parser.parse_args()
    if args.help_contract:
        print(json.dumps({
            "adapter_type": "github_actions_workflow",
            "correlation_input": "automation_task_id",
            "run_identity": ["workflow_id", "event", "head_branch", "head_sha", "display_title"],
            "success_requires": "completed workflow run with conclusion=success",
            "production_dispatch_requires_enabled_reviewed_adapter": True,
        }, sort_keys=True))
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
