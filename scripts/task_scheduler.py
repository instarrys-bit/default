#!/usr/bin/env python3
"""Deny-by-default scheduler for reviewed Python and GitHub Actions adapters."""
from __future__ import annotations

import argparse
import hashlib
from contextlib import contextmanager
import json
import os
import string
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from remote_task_queue_runtime import (
    claim_remote, complete_remote, enqueue_remote, make_store, recover_remote,
    validate_candidate, validate_envelope,
)
from task_queue_runtime import authorize, now_utc
from github_queue_store import QueueStoreError
from task_result_verifier import (
    validate_json_schema, validate_schema_definition, verify_pending_remote,
)
from github_workflow_adapter import (
    GitHubWorkflowClient, WorkflowAPIError, WorkflowDispatchOutcomeUnknown,
    WorkflowDispatchRejected, prepare_dispatch, submit_dispatch, validate_dispatch_request,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "automation" / "program_registry.json"
ADAPTERS = ROOT / "automation" / "execution_adapters.json"
ALLOWED_ARGUMENT_FIELDS = {"task_input_file", "task_id", "idempotency_key", "trace_id"}
SAFE_ENV_KEYS = {
    "PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "TEMP", "TMP",
    "SYSTEMROOT", "WINDIR", "PATHEXT",
}


def load_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def adapter_index(adapters: dict) -> dict:
    items = adapters.get("adapters")
    if adapters.get("schema_version") != 1 or not isinstance(items, list):
        raise ValueError("execution adapter inventory is invalid")
    indexed = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("execution adapter entries must be objects")
        target = item.get("target_program_id")
        if not isinstance(target, str) or not target or target in indexed:
            raise ValueError("execution adapter target IDs must be unique non-empty strings")
        indexed[target] = item
    return indexed


def validate_argv_template(template: object) -> None:
    if not isinstance(template, list) or any(not isinstance(item, str) for item in template):
        raise ValueError("argv_template must be an array of strings")
    fields = []
    for argument in template:
        try:
            parsed = list(string.Formatter().parse(argument))
        except ValueError as exc:
            raise ValueError("argv_template contains malformed braces") from exc
        for _, field, format_spec, conversion in parsed:
            if field is None:
                continue
            if field not in ALLOWED_ARGUMENT_FIELDS or format_spec or conversion:
                raise ValueError(f"argv_template uses unsupported placeholder: {field}")
            fields.append(field)
    if fields.count("task_input_file") != 1:
        raise ValueError("argv_template must include {task_input_file} exactly once")


def build_execution_plan(queue: dict, registry: dict, adapters: dict,
                         root: Path = ROOT, now: datetime | None = None) -> dict:
    now = now or now_utc()
    validate_envelope(queue)
    validate_candidate(queue, registry)
    programs = registry.get("programs")
    if not isinstance(programs, list):
        raise ValueError("program registry is invalid")
    by_id = {item.get("id"): item for item in programs if isinstance(item, dict)}
    by_target = adapter_index(adapters)
    eligible = []
    blocked = []

    for task in queue["tasks"]:
        if task.get("status") != "QUEUED":
            continue
        task_id = task["task_id"]
        try:
            not_before = datetime.fromisoformat(task["not_before"].replace("Z", "+00:00"))
            if not_before > now:
                continue
            target_id = task["target_program_id"]
            target = by_id.get(target_id)
            adapter = by_target.get(target_id)
            if target is None:
                raise ValueError("target program is not registered")
            protected_config_digest(root)
            authorize(task, by_id)
            if not isinstance(adapter, dict) or adapter.get("enabled") is not True:
                raise ValueError("target adapter is disabled")
            resource_contract = adapter.get("resource_contract")
            if target_id == "workflow_auto_sync" and resource_contract is None:
                raise ValueError("production workflow is blocked without a fenced resource contract")
            if resource_contract is not None:
                if not isinstance(resource_contract, dict) or resource_contract.get("mode") != "exclusive" or resource_contract.get("fencing_required") is not True:
                    raise ValueError("resource_contract must declare exclusive mode and mandatory fencing")
                keys = resource_contract.get("resource_keys")
                if not isinstance(keys, list) or not keys or any(not isinstance(key, str) or not key or key.startswith("/") or chr(92) in key or any(part in {"", ".", ".."} for part in key.split("/")) for key in keys) or len(keys) != len(set(keys)):
                    raise ValueError("resource_contract resource_keys must be unique canonical relative paths")
                lease_seconds = resource_contract.get("lease_seconds")
                if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or not 1 <= lease_seconds <= 21600:
                    raise ValueError("resource_contract lease_seconds must be from 1 to 21600")
            read_only_resources = adapter.get("read_only_resources", [])
            read_only_resource_digests(root, read_only_resources)
            if isinstance(resource_contract, dict) and set(read_only_resources) & set(resource_contract.get("resource_keys", [])):
                raise ValueError("a resource cannot be both read-only and exclusively writable")
            completion = adapter.get("completion", {})
            artifact_verifier = completion.get("artifact_verifier") if isinstance(completion, dict) else None
            if artifact_verifier is not None:
                if not isinstance(artifact_verifier, dict) or not isinstance(artifact_verifier.get("path"), str) or not isinstance(artifact_verifier.get("output_field"), str) or not isinstance(artifact_verifier.get("program_id"), str):
                    raise ValueError("artifact_verifier must declare a registered program_id, path and output_field")
                verifier_program = by_id.get(artifact_verifier["program_id"])
                if not isinstance(verifier_program, dict) or verifier_program.get("path") != artifact_verifier["path"] or verifier_program.get("kind") != "python_component":
                    raise ValueError("artifact verifier program identity does not match the registry")
                verifier_path = (root / artifact_verifier["path"]).resolve()
                if not verifier_path.is_relative_to(root.resolve()) or not verifier_path.is_file():
                    raise ValueError("registered artifact verifier is missing or outside the repository")
            expected_interface = (
                "reviewed" if adapter.get("adapter_type") == "python_cli"
                else "workflow_dispatch_reviewed" if adapter.get("adapter_type") == "github_actions_workflow"
                else None
            )
            if expected_interface is None or adapter.get("interface_status") != expected_interface:
                raise ValueError("target adapter interface is not reviewed for its adapter type")
            if task["requester_program_id"] not in adapter.get("allowed_callers", []):
                raise ValueError("requester is not in the adapter caller allowlist")
            timeout = adapter.get("timeout_seconds")
            policy_timeout = target.get("orchestration", {}).get("timeout_seconds")
            if (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1 or timeout > 300
                    or isinstance(policy_timeout, bool) or not isinstance(policy_timeout, int)
                    or timeout >= policy_timeout):
                raise ValueError("adapter timeout must be 1-300 seconds and shorter than the registered task lease")
            if adapter.get("adapter_type") == "python_cli":
                if adapter.get("input_contract") is None or adapter.get("output_contract") is None:
                    raise ValueError("reviewed input and output contracts are required")
                validate_schema_definition(adapter["input_contract"])
                validate_schema_definition(adapter["output_contract"])
                input_errors = validate_json_schema(task["input"], adapter["input_contract"])
                if input_errors:
                    raise ValueError("task input contract failed: " + "; ".join(input_errors[:5]))
                entrypoint = adapter.get("entrypoint")
                if (not isinstance(entrypoint, dict) or entrypoint.get("path") != target.get("path")
                        or entrypoint.get("executable") != "python3" or entrypoint.get("shell") is not False):
                    raise ValueError("entrypoint must match the registered Python component and prohibit shell execution")
                validate_argv_template(entrypoint.get("argv_template"))
                entrypoint_path = (root / entrypoint["path"]).resolve()
                if not entrypoint_path.is_relative_to(root.resolve()) or not entrypoint_path.is_file():
                    raise ValueError("registered entrypoint is missing or resolves outside the repository")
            elif adapter.get("adapter_type") == "github_actions_workflow":
                if task.get("dispatch_intent") is not None:
                    raise ValueError("persisted workflow dispatch intent requires reconciliation; redispatch is prohibited")
                workflow = adapter.get("workflow")
                if (not isinstance(workflow, dict) or workflow.get("path") != target.get("path")
                        or workflow.get("dispatchable") is not True):
                    raise ValueError("workflow path or dispatchable contract is invalid")
                preflight_task = task
                if isinstance(adapter.get("resource_contract"), dict):
                    preflight_task = dict(task)
                    preflight_task["input"] = dict(task.get("input") or {})
                    # The actual proof is minted atomically during claim_remote; plan-time
                    # validation checks only the declared string input shape.
                    preflight_task["input"]["resource_lease_proof"] = "{}"
                validate_dispatch_request(adapter, preflight_task, "main")
            else:
                raise ValueError("unsupported execution adapter type")
            eligible.append(task_id)
        except (KeyError, TypeError, ValueError) as exc:
            blocked.append({"task_id": task_id, "reason": str(exc)})

    return {"eligible_task_ids": eligible, "blocked": blocked}


class ProtectedConfigMutationError(RuntimeError):
    """Stop the scheduler if a child process changes the protected primary config."""


def protected_config_digest(root: Path = ROOT) -> str:
    path = root / "shadowrocket" / "ss.conf"
    if not path.is_file():
        raise ValueError("protected config guard unavailable: shadowrocket/ss.conf is missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_only_resource_digests(root: Path, paths: list[str]) -> dict[str, str | None]:
    if not isinstance(paths, list) or any(not isinstance(path, str) or not path or path.startswith("/") or chr(92) in path or any(part in {"", ".", ".."} for part in path.split("/")) for path in paths):
        raise ValueError("read_only_resources must contain safe repository-relative file paths")
    if len(paths) != len(set(paths)):
        raise ValueError("read_only_resources contains duplicate paths")
    result={}
    for relative in paths:
        path=(root/relative).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"read-only resource resolves outside repository: {relative}")
        if path.exists() and not path.is_file():
            raise ValueError(f"read-only resource must be a file: {relative}")
        result[relative]=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return result


def ensure_read_only_resources_unchanged(before: dict[str, str | None], root: Path) -> None:
    after=read_only_resource_digests(root,list(before))
    changed=[path for path in before if before[path]!=after[path]]
    if changed:
        raise ProtectedConfigMutationError("Capability modified declared read-only resources: "+", ".join(changed))


def ensure_protected_config_unchanged(before_digest: str, task: dict, store,
                                      registry: dict, root: Path = ROOT) -> None:
    after_digest = protected_config_digest(root)
    if after_digest == before_digest:
        return
    error = {
        "type": "protected_config_mutation_detected",
        "message": "Child program changed shadowrocket/ss.conf; scheduler stopped fail-closed.",
    }
    try:
        complete_remote(
            task["task_id"], task["lease"]["owner"], task["lease"]["token"],
            success=False, error=error, store=store, registry=registry, now=now,
        )
    finally:
        raise ProtectedConfigMutationError(error["message"])


@contextmanager
def without_parent_secrets():
    """Temporarily remove credential-like variables from the scheduler process too."""
    secret_markers = ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "PRIVATE_KEY")
    removed = {
        key: value for key, value in os.environ.items()
        if any(marker in key.upper() for marker in secret_markers)
    }
    for key in removed:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        os.environ.update(removed)


def safe_child_environment(root: Path = ROOT) -> dict[str, str]:
    """Pass only non-secret runtime basics; never inherit GitHub or runner credentials."""
    environment = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    environment["PYTHONPATH"] = os.pathsep.join((str(root), str(root / "scripts")))
    return environment


def persist_workflow_dispatch_intent(task: dict, intent: dict, store, registry: dict) -> dict:
    """Persist correlation identity before the non-idempotent GitHub dispatch call."""
    stable = {key: intent[key] for key in (
        "workflow_id", "workflow_path", "ref", "requested_head_sha",
        "task_id", "dispatch_attempt", "correlation_id", "correlation_title", "prepared_at",
    )}
    def mutate(queue):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        current = next((item for item in queue["tasks"] if item["task_id"] == task["task_id"]), None)
        if current is None or current.get("status") != "CLAIMED":
            raise ValueError("workflow task is no longer claimed")
        lease = current.get("lease") or {}
        if lease.get("owner") != task["lease"]["owner"] or lease.get("token") != task["lease"]["token"]:
            raise ValueError("workflow task lease changed before dispatch intent persistence")
        existing = current.get("dispatch_intent")
        if existing is not None:
            if existing != stable:
                raise ValueError("workflow task already has a different dispatch intent; refusing redispatch")
            return queue, existing
        current["dispatch_intent"] = stable
        queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, stable
    return store.mutate(mutate)


def clear_workflow_dispatch_intent(task: dict, store, registry: dict) -> None:
    """Clear an intent only after GitHub explicitly rejects the dispatch request."""
    def mutate(queue):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        current = next((item for item in queue["tasks"] if item["task_id"] == task["task_id"]), None)
        if current is None or current.get("status") != "CLAIMED":
            raise ValueError("workflow task is no longer claimed")
        lease = current.get("lease") or {}
        if lease.get("owner") != task["lease"]["owner"] or lease.get("token") != task["lease"]["token"]:
            raise ValueError("workflow task lease changed before dispatch intent clear")
        current.pop("dispatch_intent", None)
        queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, None
    store.mutate(mutate)


def execute_claimed_workflow_task(task: dict, adapter: dict, store, registry: dict,
                                   adapters: dict, now: datetime | None = None) -> dict:
    """Persist intent, dispatch once, then move the task to independent verification."""
    now = now or now_utc()
    try:
        client = GitHubWorkflowClient(
            store.repository, token=store.token, timeout=adapter["timeout_seconds"]
        )
        dispatch_task = dict(task)
        dispatch_task["input"] = dict(task.get("input") or {})
        resource_lease = task.get("resource_lease")
        if isinstance(adapter.get("resource_contract"), dict):
            if not isinstance(resource_lease, dict) or resource_lease.get("status") != "ACTIVE":
                raise ValueError("workflow dispatch requires an active task resource lease")
            resources = resource_lease.get("resources")
            if not isinstance(resources, dict) or set(resources) != set(adapter["resource_contract"].get("resource_keys", [])):
                raise ValueError("task resource lease does not match the adapter's reviewed resource set")
            dispatch_task["input"]["resource_lease_proof"] = json.dumps(resources, sort_keys=True, separators=(",", ":"))
        prepared = prepare_dispatch(client, adapter, dispatch_task, ref=store.branch)
        persisted = persist_workflow_dispatch_intent(task, prepared, store, registry)
        intent = dict(persisted)
        intent["inputs"] = prepared["inputs"]
        try:
            result = submit_dispatch(client, intent)
        except WorkflowDispatchOutcomeUnknown as exc:
            result = dict(persisted)
            result["dispatch_state"] = "unknown"
            result["dispatch_uncertainty"] = str(exc)
        except WorkflowDispatchRejected as exc:
            clear_workflow_dispatch_intent(task, store, registry)
            error = {"type": "workflow_dispatch_rejected", "message": str(exc)}
            completed = complete_remote(
                task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                success=False, error=error, store=store, registry=registry, now=now,
            )
            return {"task_id": task["task_id"], "status": completed["status"], "error": error}
        pending = complete_remote(
            task["task_id"], task["lease"]["owner"], task["lease"]["token"],
            success=True, result=result, store=store, registry=registry, now=now,
        )
        verification = verify_pending_remote(
            store, registry, adapters, now, workflow_client=client
        )
        snapshot = store.read().document
        final_task = next(item for item in snapshot["tasks"] if item["task_id"] == task["task_id"])
        return {
            "task_id": task["task_id"],
            "worker_completion_status": pending["status"],
            "status": final_task["status"],
            "dispatch_state": result["dispatch_state"],
            "verification": verification,
        }
    except (WorkflowAPIError, ValueError, OSError) as exc:
        error = {"type": "workflow_dispatch_preflight_failed", "message": str(exc)[:1000]}
        completed = complete_remote(
            task["task_id"], task["lease"]["owner"], task["lease"]["token"],
            success=False, error=error, store=store, registry=registry, now=now,
        )
        return {"task_id": task["task_id"], "status": completed["status"], "error": error}


def execute_claimed_task(task: dict, adapter: dict, store, registry: dict,
                         adapters: dict, root: Path = ROOT,
                         now: datetime | None = None) -> dict:
    now = now or now_utc()
    if adapter.get("adapter_type") == "github_actions_workflow":
        return execute_claimed_workflow_task(task, adapter, store, registry, adapters, now)
    entrypoint = adapter["entrypoint"]
    script_path = (root / entrypoint["path"]).resolve()
    input_errors = validate_json_schema(task["input"], adapter["input_contract"])
    if input_errors:
        error = {
            "type": "input_contract_changed_after_plan",
            "message": "Claimed task input no longer satisfies the reviewed input contract.",
            "details": input_errors[:20],
        }
        completed_task = complete_remote(
            task["task_id"], task["lease"]["owner"], task["lease"]["token"],
            success=False, error=error, store=store, registry=registry, now=now_utc(),
        )
        return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}
    protected_digest = protected_config_digest(root)
    read_only_before = read_only_resource_digests(root, adapter.get("read_only_resources", []))
    argv_values = {
        "task_id": task["task_id"],
        "idempotency_key": task["idempotency_key"],
        "trace_id": task["trace_id"],
    }
    with tempfile.TemporaryDirectory(prefix="automation-task-") as directory:
        input_path = Path(directory) / "task-input.json"
        input_path.write_text(json.dumps(task["input"], ensure_ascii=False), encoding="utf-8")
        argv_values["task_input_file"] = str(input_path)
        argv = [argument.format_map(argv_values) for argument in entrypoint["argv_template"]]
        command = [sys.executable, str(script_path), *argv]
        child_env = safe_child_environment(root)
        resource_contract = adapter.get("resource_contract")
        if isinstance(resource_contract, dict):
            resource_lease = task.get("resource_lease")
            if not isinstance(resource_lease, dict) or resource_lease.get("status") != "ACTIVE":
                raise ValueError("Python capability dispatch requires an active resource lease")
            resources = resource_lease.get("resources")
            if not isinstance(resources, dict) or set(resources) != set(resource_contract.get("resource_keys", [])):
                raise ValueError("Python task resource lease does not match its reviewed resource contract")
            snapshot_path = Path(directory) / "task-queue-lease-snapshot.json"
            snapshot_path.write_text(json.dumps(store.read().document, ensure_ascii=False), encoding="utf-8")
            snapshot_path.chmod(0o400)
            child_env.update({
                "AUTOMATION_QUEUE_SNAPSHOT": str(snapshot_path),
                "AUTOMATION_TASK_ID": task["task_id"],
                "AUTOMATION_WORKER_ID": task["lease"]["owner"],
                "AUTOMATION_TASK_LEASE_TOKEN": task["lease"]["token"],
                "AUTOMATION_RESOURCE_LEASE_PROOF": json.dumps(resources, sort_keys=True, separators=(",", ":")),
            })
        try:
            with without_parent_secrets():
                completed = subprocess.run(
                    command,
                    cwd=root,
                    env=child_env,
                    shell=False,
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    timeout=adapter["timeout_seconds"],
                    check=False,
                )
        except subprocess.TimeoutExpired:
            ensure_protected_config_unchanged(protected_digest, task, store, registry, root)
            try:
                ensure_read_only_resources_unchanged(read_only_before, root)
            except ProtectedConfigMutationError as exc:
                error = {"type": "read_only_resource_mutation_detected", "message": str(exc)}
            else:
                error = {"type": "execution_timeout", "message": "Registered program exceeded its adapter timeout."}
            completed_task = complete_remote(
                task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                success=False, error=error, store=store, registry=registry, now=now_utc(),
            )
            return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}
        except OSError as exc:
            error = {"type": "execution_start_failed", "message": str(exc)[:1000]}
            completed_task = complete_remote(
                task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                success=False, error=error, store=store, registry=registry, now=now_utc(),
            )
            return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}

        ensure_protected_config_unchanged(protected_digest, task, store, registry, root)
        try:
            ensure_read_only_resources_unchanged(read_only_before, root)
        except ProtectedConfigMutationError as exc:
            error = {"type": "read_only_resource_mutation_detected", "message": str(exc)}
            completed_task = complete_remote(
                task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                success=False, error=error, store=store, registry=registry, now=now_utc(),
            )
            return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}

        if completed.returncode != 0:
            error = {
                "type": "program_exit_nonzero",
                "exit_code": completed.returncode,
                "stderr": completed.stderr[-2000:],
            }
            completed_task = complete_remote(
                task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                success=False, error=error, store=store, registry=registry, now=now_utc(),
            )
            return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}

        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result = None
        if not isinstance(result, dict):
            error = {
                "type": "invalid_program_output",
                "message": "Program stdout must contain one JSON object.",
                "stdout": completed.stdout[-2000:],
            }
            completed_task = complete_remote(
                task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                success=False, error=error, store=store, registry=registry, now=now_utc(),
            )
            return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}

        artifact_verifier = adapter.get("completion", {}).get("artifact_verifier")
        if artifact_verifier is not None:
            output_field = artifact_verifier["output_field"]
            if output_field in result:
                error = {"type": "artifact_verifier_output_collision", "message": f"program output already contains reserved field {output_field}"}
                completed_task = complete_remote(
                    task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                    success=False, error=error, store=store, registry=registry, now=now_utc(),
                )
                return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}
            verifier_path = (root / artifact_verifier["path"]).resolve()
            try:
                with tempfile.TemporaryDirectory(prefix="artifact-verifier-") as verifier_directory:
                    result_path = Path(verifier_directory) / "task-result.json"
                    result_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                    verifier_command = [sys.executable, str(verifier_path), "--result-json-file", str(result_path)]
                    verified = subprocess.run(
                        verifier_command, cwd=root, env=safe_child_environment(root),
                        shell=False, capture_output=True, text=True,
                        stdin=subprocess.DEVNULL, timeout=min(adapter["timeout_seconds"], 60), check=False,
                    )
            except subprocess.TimeoutExpired:
                verified = None
            if verified is None or verified.returncode != 0:
                error = {"type": "independent_artifact_verification_failed",
                         "message": "Independent artifact verifier did not complete successfully.",
                         "stderr": verified.stderr[-2000:] if verified is not None else "verifier timed out"}
                completed_task = complete_remote(
                    task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                    success=False, error=error, store=store, registry=registry, now=now_utc(),
                )
                return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}
            try:
                verification_result = json.loads(verified.stdout)
            except json.JSONDecodeError:
                verification_result = None
            if not isinstance(verification_result, dict) or verification_result.get("valid") is not True:
                error = {"type": "independent_artifact_verification_invalid_output",
                         "message": "Independent artifact verifier must emit one JSON object with valid=true.",
                         "stdout": verified.stdout[-2000:]}
                completed_task = complete_remote(
                    task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                    success=False, error=error, store=store, registry=registry, now=now_utc(),
                )
                return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}
            result[output_field] = verification_result
            try:
                ensure_read_only_resources_unchanged(read_only_before, root)
            except ProtectedConfigMutationError as exc:
                error = {"type": "read_only_resource_mutation_detected", "message": str(exc)}
                completed_task = complete_remote(
                    task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                    success=False, error=error, store=store, registry=registry, now=now_utc(),
                )
                return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}

        pending = complete_remote(
            task["task_id"], task["lease"]["owner"], task["lease"]["token"],
            success=True, result=result, store=store, registry=registry, now=now_utc(),
        )
        verification = verify_pending_remote(store, registry, adapters, now_utc())
        snapshot = store.read().document
        final_task = next(item for item in snapshot["tasks"] if item["task_id"] == task["task_id"])
        return {
            "task_id": task["task_id"],
            "worker_completion_status": pending["status"],
            "status": final_task["status"],
            "verification": verification,
        }


def enqueue_auto_sync_task(store, registry: dict, *, idempotency_key: str,
                           priority: int = 80, input_payload: dict | None = None) -> dict:
    """Enqueue the production audit only through the top-level Watchdog identity."""
    if input_payload is None:
        input_payload = {}
    if not isinstance(input_payload, dict):
        raise ValueError("workflow task input must be an object")
    result = enqueue_remote({
        "idempotency_key": idempotency_key,
        "requester_program_id": "workflow_automation_watchdog",
        "target_program_id": "workflow_auto_sync",
        "capability": "deterministic_audit",
        "priority": priority,
        "input": input_payload,
    }, store, registry)
    task = result["task"]
    return {
        "created": result["created"],
        "task_id": task["task_id"],
        "status": task["status"],
        "idempotency_key": task["idempotency_key"],
    }


def run_scheduler_once(store, registry: dict, adapters: dict, *,
                       worker_id: str, max_tasks: int = 1,
                       root: Path = ROOT, now: datetime | None = None) -> dict:
    if not isinstance(max_tasks, int) or isinstance(max_tasks, bool) or not 1 <= max_tasks <= 10:
        raise ValueError("max_tasks must be an integer from 1 to 10")
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    fixed_now = now
    initial_now = now or now_utc()
    recovered = recover_remote(store, registry, initial_now)
    initial_verification = verify_pending_remote(store, registry, adapters, initial_now)
    processed = []
    blocked_seen = {}

    for _ in range(max_tasks):
        snapshot = store.read().document
        iteration_now = fixed_now or now_utc()
        plan = build_execution_plan(snapshot, registry, adapters, root, iteration_now)
        for item in plan["blocked"]:
            blocked_seen[item["task_id"]] = item["reason"]
        eligible = set(plan["eligible_task_ids"])
        if not eligible:
            break
        resource_keys_by_target = {
            item["target_program_id"]: item["resource_contract"]
            for item in adapters.get("adapters", [])
            if isinstance(item, dict) and isinstance(item.get("resource_contract"), dict)
        }
        task = claim_remote(
            worker_id, store, registry, eligible_task_ids=eligible,
            resource_keys_by_target=resource_keys_by_target, now=iteration_now
        )
        if task is None:
            continue
        adapter = adapter_index(adapters)[task["target_program_id"]]
        processed.append(execute_claimed_task(task, adapter, store, registry, adapters, root, now))

    final_snapshot = store.read().document
    validate_candidate(final_snapshot, registry)
    return {
        "processed_count": len(processed),
        "processed": processed,
        "blocked": [{"task_id": key, "reason": value} for key, value in sorted(blocked_seen.items())],
        "initial_verification": initial_verification,
        "recovered_count": len(recovered),
        "queue_revision": final_snapshot["revision"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--queue-path", default="automation/task_queue.json")
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--adapters", type=Path, default=ADAPTERS)
    parser.add_argument("--worker-id", default=os.environ.get("GITHUB_RUN_ID") or ("scheduler-" + uuid.uuid4().hex[:12]))
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument("--token-stdin", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--priority", type=int, default=80)
    parser.add_argument("--input-json", default="{}")
    parser.add_argument("command", choices=["plan", "run-once", "enqueue-auto-sync"])
    args = parser.parse_args()
    try:
        token = sys.stdin.read().strip() if args.token_stdin else None
        if args.command in {"run-once", "enqueue-auto-sync"} and not token:
            raise ValueError(f"{args.command} requires a queue token supplied through --token-stdin")
        store = make_store(args.repository, args.branch, args.queue_path, token=token)
        registry = load_object(args.registry, "program registry")
        adapters = load_object(args.adapters, "execution adapter inventory")
        if args.command == "plan":
            plan = build_execution_plan(store.read().document, registry, adapters)
            print(json.dumps(plan, ensure_ascii=False))
        elif args.command == "enqueue-auto-sync":
            if not isinstance(args.idempotency_key, str) or not args.idempotency_key:
                raise ValueError("enqueue-auto-sync requires --idempotency-key")
            if not 0 <= args.priority <= 100:
                raise ValueError("--priority must be an integer from 0 to 100")
            try:
                input_payload = json.loads(args.input_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"--input-json is invalid JSON: {exc}") from exc
            print(json.dumps(enqueue_auto_sync_task(
                store, registry, idempotency_key=args.idempotency_key,
                priority=args.priority, input_payload=input_payload,
            ), ensure_ascii=False))
        else:
            print(json.dumps(run_scheduler_once(
                store, registry, adapters, worker_id=args.worker_id,
                max_tasks=args.max_tasks,
            ), ensure_ascii=False))
        return 0
    except (ValueError, OSError, QueueStoreError, ProtectedConfigMutationError) as exc:
        print(f"SCHEDULER ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
