#!/usr/bin/env python3
"""Deny-by-default scheduler for reviewed Python and GitHub Actions adapters."""
from __future__ import annotations


import argparse
import base64
import hashlib
import re
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
    claim_remote, complete_remote, enqueue_remote, make_store, recover_remote, resolve_superseded_dead_letters,
    validate_candidate, validate_envelope,
)
from task_queue_runtime import (
    authorize, manual_authorization_context_from_environment,
    validate_manual_authorization, now_utc,
)
from github_queue_store import QueueStoreError
from resource_lease_runtime import assert_resource_lease, claimed_task
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
    "SYSTEMROOT", "WINDIR", "PATHEXT", "RUNNER_TEMP",
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


def assert_current_production_input(task: dict, root: Path = ROOT) -> str:
    payload = task.get("input") if isinstance(task, dict) else None
    if not isinstance(payload, dict):
        raise ValueError("production task input must be an object")
    decision = payload.get("production_decision")
    if decision not in {"INPUT_CHANGED", "SCHEDULE_DUE", "RECOVERY_REQUIRED", "USER_AUTHORIZED_MANUAL_AUDIT"}:
        raise ValueError("production task has no recognized production decision")
    expected = payload.get("production_fingerprint")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("production task is missing a valid SHA-256 input fingerprint")
    from production_intent import load_manifest, compute_fingerprint
    manifest = load_manifest(Path(root) / "automation" / "production_inputs.json")
    actual = compute_fingerprint(Path(root), manifest)
    if expected != actual:
        raise ValueError("queued production task input fingerprint is stale; Watchdog must supersede and enqueue the current main snapshot")
    return actual


def supersede_stale_queued_production_tasks(store, registry: dict, root: Path = ROOT) -> list[str]:
    """Cancel only unclaimed queued production work whose fingerprint no longer matches main."""
    snapshot = store.read().document
    candidates = [
        task for task in snapshot.get("tasks", [])
        if isinstance(task, dict)
        and task.get("target_program_id") == "workflow_auto_sync"
        and task.get("status") == "QUEUED"
        and task.get("lease") is None
        and task.get("dispatch_intent") is None
        and isinstance(task.get("input"), dict)
        and task["input"].get("production_decision") in {"INPUT_CHANGED", "SCHEDULE_DUE", "RECOVERY_REQUIRED", "USER_AUTHORIZED_MANUAL_AUDIT"}
    ]
    if not candidates:
        return []
    from production_intent import load_manifest, compute_fingerprint
    manifest = load_manifest(Path(root) / "automation" / "production_inputs.json")
    current = compute_fingerprint(Path(root), manifest)
    def mutate(queue: dict):
        changed = []
        for task in queue.get("tasks", []):
            payload = task.get("input") if isinstance(task, dict) else None
            if (task.get("target_program_id") != "workflow_auto_sync"
                    or task.get("status") != "QUEUED"
                    or task.get("lease") is not None
                    or task.get("dispatch_intent") is not None
                    or not isinstance(payload, dict)
                    or payload.get("production_decision") not in {"INPUT_CHANGED", "SCHEDULE_DUE", "RECOVERY_REQUIRED", "USER_AUTHORIZED_MANUAL_AUDIT"}
                    or payload.get("production_fingerprint") == current):
                continue
            task["status"] = "CANCELLED"
            task["state_history"].append("CANCELLED")
            task["last_error"] = {
                "type": "stale_production_input_superseded",
                "message": "Queued production task was cancelled before claim because its input fingerprint no longer matches current main.",
                "current_production_fingerprint": current,
            }
            changed.append(task["task_id"])
        if changed:
            queue["revision"] += 1
            validate_candidate(queue, registry)
        return queue, changed
    return store.mutate(mutate)

def production_source_assessment_gate(tasks: list, root: Path = ROOT) -> bool:
    """Require a verified, non-activating Assessment for the newest Discovery in independent mode."""
    control = load_object(Path(root) / "automation" / "production_control.json", "production control")
    mode = control.get("source_discovery_mode")
    if mode == "monolithic_fallback":
        return True
    if mode != "independent":
        return False
    if not isinstance(tasks, list):
        return False
    from source_handoff_policy import latest_verified_assessed_discovery
    return latest_verified_assessed_discovery(tasks) is not None


def build_execution_plan(queue: dict, registry: dict, adapters: dict,
                         root: Path = ROOT, now: datetime | None = None) -> dict:
    now = now or now_utc()
    validate_envelope(queue)
    validate_candidate(queue, registry)
    dispatch_mode = production_dispatch_mode(root)
    if dispatch_mode != "enabled":
        return {
            "dispatch_mode": dispatch_mode,
            "read_only": True,
            "queue_revision": queue.get("revision"),
            "eligible_task_ids": [],
            "blocked": [
                {"task_id": task.get("task_id"), "reason": f"production dispatch is {dispatch_mode}; read-only planning only"}
                for task in queue.get("tasks", [])
                if isinstance(task, dict) and task.get("status") == "QUEUED"
            ],
        }
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
            if target_id == "workflow_auto_sync":
                assert_current_production_input(task, root)
                if not production_source_assessment_gate(queue.get("tasks", []), root):
                    raise ValueError(
                        "production audit is blocked until the latest independent Discovery has a verified non-activating Assessment"
                    )
            target = by_id.get(target_id)
            adapter = by_target.get(target_id)
            if target is None:
                raise ValueError("target program is not registered")
            protected_config_digest(root)
            validate_manual_authorization(task, manual_authorization_context_from_environment())
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
            publish_resources = adapter.get("publish_resources", [])
            write_resources = adapter.get("write_resources", [])
            if not isinstance(publish_resources, list) or len(publish_resources) != len(set(publish_resources)):
                raise ValueError("publish_resources must be a unique path list")
            if not isinstance(write_resources, list) or len(write_resources) != len(set(write_resources)):
                raise ValueError("write_resources must be a unique path list")
            if write_resources or publish_resources:
                resource_keys = resource_contract.get("resource_keys", []) if isinstance(resource_contract, dict) else []
                validate_repository_write_scope(write_resources, publish_resources, resource_keys)
            if publish_resources:
                if not isinstance(adapter.get("completion", {}).get("artifact_verifier"), dict):
                    raise ValueError("publishing task artifacts requires an independent artifact verifier")
                output_contract = adapter.get("output_contract")
                if not isinstance(output_contract, dict) or "artifact_publication" not in output_contract.get("required", []):
                    raise ValueError("publishing adapter output contract must require artifact_publication")
            read_only_resources = adapter.get("read_only_resources", [])
            read_only_digests = read_only_resource_digests(root, read_only_resources)
            required_read_only = adapter.get("required_read_only_resources", [])
            if (not isinstance(required_read_only,list)
                    or any(path not in read_only_resources for path in required_read_only)):
                raise ValueError("required_read_only_resources must be a subset of read_only_resources")
            missing_inputs=[path for path in required_read_only if read_only_digests.get(path) is None]
            if missing_inputs:
                raise ValueError("required input artifacts are missing: "+", ".join(missing_inputs))
            dependency = adapter.get("dependency_contract")
            if dependency is not None:
                if not isinstance(dependency, dict):
                    raise ValueError("dependency_contract must be an object")
                predecessor_id = dependency.get("predecessor_program_id")
                artifact_path = dependency.get("artifact_path")
                workflow_name = dependency.get("producer_workflow_name")
                proof = task.get("input", {}).get("predecessor")
                if (not isinstance(predecessor_id, str) or not isinstance(artifact_path, str)
                        or not isinstance(workflow_name, str) or artifact_path not in required_read_only
                        or not isinstance(proof, dict)):
                    raise ValueError("typed predecessor contract or task proof is incomplete")
                expected_proof = {
                    "program_id": predecessor_id,
                    "workflow_name": workflow_name,
                    "artifact_path": artifact_path,
                }
                if any(proof.get(key) != value for key, value in expected_proof.items()):
                    raise ValueError("typed predecessor identity does not match the reviewed contract")
                if (not isinstance(proof.get("workflow_run_id"), str)
                        or not proof["workflow_run_id"].isdigit()
                        or not isinstance(proof.get("workflow_head_sha"), str)
                        or not re.fullmatch(r"[0-9a-f]{40}", proof["workflow_head_sha"])
                        or not isinstance(proof.get("artifact_sha256"), str)
                        or not re.fullmatch(r"[0-9a-f]{64}", proof["artifact_sha256"])):
                    raise ValueError("typed predecessor run or artifact digest is malformed")
                if read_only_digests.get(artifact_path) != proof["artifact_sha256"]:
                    raise ValueError("typed predecessor artifact digest changed before task execution")
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
    path = root / "modules" / "uu.conf"
    if not path.is_file():
        raise ValueError("protected config guard unavailable: modules/uu.conf is missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def external_read_only_resource_root(root: Path, relative: str) -> Path:
    """Resolve the exact discovery predecessor from the verified runner-local artifact only."""
    if relative != "sources/discovered_sources.json":
        return root
    supplied = os.environ.get("AUTOMATION_PREDECESSOR_ARTIFACT_ROOT")
    if not supplied:
        return root
    artifact_root = Path(supplied).resolve()
    runner_temp = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
    if not artifact_root.is_relative_to(runner_temp) or artifact_root == root.resolve():
        raise ValueError("predecessor artifact root must be isolated under RUNNER_TEMP")
    return artifact_root


def read_only_resource_digests(root: Path, paths: list[str]) -> dict[str, str | None]:
    if not isinstance(paths, list) or any(not isinstance(path, str) or not path or path.startswith("/") or chr(92) in path or any(part in {"", ".", ".."} for part in path.split("/")) for path in paths):
        raise ValueError("read_only_resources must contain safe repository-relative file paths")
    if len(paths) != len(set(paths)):
        raise ValueError("read_only_resources contains duplicate paths")
    result={}
    for relative in paths:
        resource_root = external_read_only_resource_root(root, relative)
        path=(resource_root/relative).resolve()
        if not path.is_relative_to(resource_root.resolve()):
            raise ValueError(f"read-only resource resolves outside its authorized root: {relative}")
        if path.exists() and not path.is_file():
            raise ValueError(f"read-only resource must be a file: {relative}")
        digest=hashlib.sha256()
        found=False
        if path.is_file():
            digest.update(b"legacy-json\\0")
            digest.update(path.read_bytes())
            found=True
        manifest=path.with_name(path.name + ".manifest.json")
        if manifest.is_file():
            try:
                value=json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError,json.JSONDecodeError) as exc:
                raise ValueError(f"read-only document manifest is invalid: {relative}") from exc
            if not isinstance(value,dict):
                raise ValueError(f"read-only document manifest must be an object: {relative}")
            if not manifest.resolve().is_relative_to(resource_root.resolve()):
                raise ValueError(f"read-only document manifest resolves outside repository: {relative}")
            directory=value.get("shard_directory")
            shards=value.get("shards")
            if (value.get("logical_path")!=path.name or not isinstance(directory,str)
                    or Path(directory).name!=directory or not isinstance(shards,list)):
                raise ValueError(f"read-only document manifest identity is invalid: {relative}")
            digest.update(b"manifest\\0")
            digest.update(manifest.read_bytes())
            for shard in shards:
                name=shard.get("file") if isinstance(shard,dict) else None
                if not isinstance(name,str) or Path(name).name!=name or not name.endswith(".jsonl"):
                    raise ValueError(f"read-only document shard entry is invalid: {relative}")
                shard_path=manifest.parent/directory/name
                if not shard_path.resolve().is_relative_to(resource_root.resolve()):
                    raise ValueError(f"read-only document shard resolves outside repository: {relative}/{directory}/{name}")
                if not shard_path.is_file():
                    raise ValueError(f"read-only document shard is missing: {relative}/{directory}/{name}")
                digest.update(name.encode("utf-8")+b"\\0")
                digest.update(hashlib.sha256(shard_path.read_bytes()).digest())
            found=True
        result[relative]=digest.hexdigest() if found else None
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
        "message": "Child program changed modules/uu.conf; scheduler stopped fail-closed.",
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
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for key in ("AUTOMATION_PREDECESSOR_ARTIFACT_ROOT", "AUTOMATION_ARTIFACT_ROOT"):
        if os.environ.get(key):
            environment[key] = os.environ[key]
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


def is_generated_python_cache_path(path: str) -> bool:
    parts=Path(path).parts
    return "__pycache__" in parts or path.endswith(".pyc")


def generated_python_cache_paths(paths) -> list[str]:
    """Return disposable Python bytecode paths that must never be published."""
    return sorted({path for path in paths if is_generated_python_cache_path(path)})


def validate_repository_write_scope(write_resources: list, publish_resources: list, resource_keys: list) -> None:
    """Require every repository mutation to be explicitly fenced and non-protected.

    This is a per-capability resource contract, not a global rulesets/** write
    restriction. The production auto_sync publisher separately stages only the
    three declared ruleset deliverables under its own workflow-level path fence.
    """
    if not isinstance(write_resources, list) or not isinstance(publish_resources, list):
        raise ValueError("repository write and publish resources must be lists")
    if not isinstance(resource_keys, list):
        raise ValueError("resource contract keys must be a list")
    if len(write_resources) != len(set(write_resources)) or len(publish_resources) != len(set(publish_resources)):
        raise ValueError("repository write and publish resources must be unique")
    if any(path not in write_resources for path in publish_resources):
        raise ValueError("publish_resources must be a subset of write_resources")
    for path in write_resources + publish_resources:
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or chr(92) in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
        ):
            raise ValueError("repository write resource contains an unsafe path")
        if path == "modules" or path.startswith("modules/") or path.lower().endswith(".js"):
            raise ValueError("repository write resource targets protected modules or JavaScript")
        if path not in resource_keys:
            raise ValueError("repository write resource is not declared in the exclusive resource contract")


def publishable_resource_path(path: str, resources: list[str]) -> bool:
    """Accept only exact logical outputs and their known JSONL document-store children."""
    for logical in resources:
        base=re.escape(logical)
        if path in {logical, logical + ".manifest.json"}:
            return True
        if re.fullmatch(base + r"\.parts-[0-9a-f]{16}/part-[0-9]{6}\.jsonl", path):
            return True
    return False


def assert_live_task_resource_proofs(task: dict, adapter: dict, store) -> dict:
    """Re-read the durable queue and validate every lease before artifact publication."""
    snapshot=store.read().document
    task_id=task["task_id"]
    worker_id=task["lease"]["owner"]
    task_token=task["lease"]["token"]
    live_task=claimed_task(snapshot,task_id,worker_id,task_token,now_utc())
    live_proof=live_task.get("resource_lease")
    expected=task.get("resource_lease")
    if (not isinstance(live_proof,dict) or live_proof.get("status")!="ACTIVE"
            or not isinstance(expected,dict) or live_proof.get("resources")!=expected.get("resources")):
        raise ValueError("live task resource lease proof changed before artifact publication")
    resources=expected.get("resources")
    contract=adapter.get("resource_contract",{})
    if not isinstance(resources,dict) or set(resources)!=set(contract.get("resource_keys",[])):
        raise ValueError("task resource lease does not match the reviewed publish contract")
    for path,proof in resources.items():
        assert_resource_lease(
            snapshot,task_id=task_id,worker_id=worker_id,task_lease_token=task_token,
            resource_path=path,lease_id=proof.get("lease_id"),
            fencing_token=proof.get("fencing_token"),now=now_utc(),
        )
    return resources


def publish_task_artifacts(task: dict, adapter: dict, store, protected_digest: str,
                           read_only_before: dict[str,str|None], root: Path = ROOT) -> dict:
    """Commit only allowlisted persistent artifacts after independent verification."""
    resources=adapter.get("publish_resources",[])
    if not resources:
        return {"published":False,"commit_sha":"","paths":[]}
    write_resources=adapter.get("write_resources",[])
    contract = adapter.get("resource_contract", {})
    keys = contract.get("resource_keys", []) if isinstance(contract, dict) else []
    validate_repository_write_scope(write_resources, resources, keys)

    def run_git(args, env, *, timeout=45):
        completed=subprocess.run(
            ["git",*args],cwd=root,env=env,shell=False,capture_output=True,
            text=True,stdin=subprocess.DEVNULL,timeout=timeout,check=False,
        )
        if completed.returncode!=0:
            raise RuntimeError("artifact publication git command failed: "+completed.stderr[-1500:])
        return completed.stdout

    env=os.environ.copy()
    for key in list(env):
        if any(marker in key.upper() for marker in ("TOKEN","SECRET","PASSWORD","CREDENTIAL","PRIVATE_KEY")):
            env.pop(key,None)
    auth=base64.b64encode(("x-access-token:"+store.token).encode("utf-8")).decode("ascii")
    env.update({
        "GIT_CONFIG_COUNT":"1",
        "GIT_CONFIG_KEY_0":"http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0":"AUTHORIZATION: basic "+auth,
        "GIT_TERMINAL_PROMPT":"0",
    })
    def allowed_workspace(path):
        return publishable_resource_path(path,write_resources)
    def allowed_publish(path):
        return publishable_resource_path(path,resources)

    changed=set()
    for command in (
        ["diff","--name-only","-z"],
        ["diff","--cached","--name-only","-z"],
        ["ls-files","--others","--exclude-standard","-z"],
    ):
        changed.update(
            item for item in run_git(command,env).split("\0")
            if item and not is_generated_python_cache_path(item)
        )
    outside=sorted(path for path in changed if not allowed_workspace(path))
    if outside:
        raise ValueError("refusing to publish unrelated workspace changes: "+", ".join(outside[:20]))
    staged_before={item for item in run_git(["diff","--cached","--name-only","-z"],env).split("\0") if item}
    staged_cache=generated_python_cache_paths(staged_before)
    if staged_cache:
        run_git(["restore","--staged","--",*staged_cache],env)
        staged_before.difference_update(staged_cache)
    outside=sorted(path for path in staged_before if not allowed_publish(path))
    if outside:
        raise ValueError("pre-staged files exceed the persistent artifact allowlist: "+", ".join(outside[:20]))
    publish_changed={path for path in changed if allowed_publish(path)}
    if publish_changed:
        run_git(["add","-A","--",*sorted(publish_changed)],env)
    staged={item for item in run_git(["diff","--cached","--name-only","-z"],env).split("\0") if item}
    staged_cache=generated_python_cache_paths(staged)
    if staged_cache:
        run_git(["restore","--staged","--",*staged_cache],env)
        staged.difference_update(staged_cache)
    outside=sorted(path for path in staged if not allowed_publish(path))
    if outside:
        raise ValueError("staged artifact set exceeds publish allowlist: "+", ".join(outside[:20]))
    if not staged:
        return {"published":False,"commit_sha":"","paths":[]}
    run_git(["diff","--cached","--check"],env)
    run_git(["config","user.name","github-actions[bot]"],env)
    run_git(["config","user.email","41898282+github-actions[bot]@users.noreply.github.com"],env)
    assert_live_task_resource_proofs(task,adapter,store)
    run_git(["commit","-m","Publish bounded source assessment artifacts"],env)
    run_git(["fetch","origin","main"],env)
    run_git(["rebase","origin/main"],env)
    if protected_config_digest(root)!=protected_digest:
        raise ProtectedConfigMutationError("Protected config changed while rebasing assessment artifact publication.")
    ensure_read_only_resources_unchanged(read_only_before,root)
    assert_live_task_resource_proofs(task,adapter,store)
    run_git(["push","origin","HEAD:main"],env)
    published_sha=run_git(["rev-parse","HEAD"],env).strip()
    remote=run_git(["ls-remote","origin","refs/heads/main"],env).strip().split()
    if not remote or remote[0]!=published_sha:
        raise RuntimeError("artifact publication could not be independently confirmed on main")
    return {"published":True,"commit_sha":published_sha,"paths":sorted(staged)}


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
                "AUTOMATION_QUEUE_REPOSITORY": store.repository,
                "AUTOMATION_QUEUE_BRANCH": store.branch,
                "AUTOMATION_QUEUE_PATH": store.path,
                "AUTOMATION_QUEUE_TOKEN": store.token,
                "AUTOMATION_TASK_PROCESS": "1",
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
                publication=publish_task_artifacts(task,adapter,store,protected_digest,read_only_before,root)
                if adapter.get("publish_resources"):
                    result["artifact_publication"]=publication
                ensure_read_only_resources_unchanged(read_only_before, root)
            except ProtectedConfigMutationError as exc:
                error = {"type": "read_only_resource_mutation_detected", "message": str(exc)}
                completed_task = complete_remote(
                    task["task_id"], task["lease"]["owner"], task["lease"]["token"],
                    success=False, error=error, store=store, registry=registry, now=now_utc(),
                )
                return {"task_id": task["task_id"], "status": completed_task["status"], "error": error}
            except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                error = {"type": "artifact_publication_failed", "message": str(exc)[:1500]}
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


def enqueue_source_discovery_task(store, registry: dict, *, idempotency_key: str,
                                   priority: int = 55) -> dict:
    """Enqueue one daily Discovery task plus at most one recovery after a dead-letter."""
    match = re.fullmatch(
        r"source-discovery:(\d{4}-\d{2}-\d{2})(?::([0-9a-f]{12}))?(?::recovery:(1))?",
        idempotency_key or "",
    )
    if not match:
        raise ValueError(
            "source discovery requires a UTC-day key with optional 12-hex discovery revision "
            "and one recovery key: source-discovery:YYYY-MM-DD[:revision][:recovery:1]"
        )
    try:
        datetime.strptime(match.group(1), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("source discovery idempotency key contains an invalid UTC date") from exc
    if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
        raise ValueError("source discovery priority must be from 0 to 100")
    precondition = None
    if match.group(3):
        base_key = f"source-discovery:{match.group(1)}" + (f":{match.group(2)}" if match.group(2) else "")
        def require_dead_lettered_daily_task(queue):
            base_task = next((item for item in queue.get("tasks", [])
                              if item.get("idempotency_key") == base_key), None)
            if base_task is None or base_task.get("status") != "DEAD_LETTER":
                raise ValueError("source discovery recovery requires a dead-lettered matching Discovery task")
            other_recoveries = [
                item for item in queue.get("tasks", [])
                if isinstance(item.get("idempotency_key"), str)
                and item.get("idempotency_key", "").startswith(base_key + ":recovery:")
                and item.get("idempotency_key") != idempotency_key
            ]
            if other_recoveries:
                raise ValueError("only one source discovery recovery attempt is allowed for this revision")
        precondition = require_dead_lettered_daily_task
    result = enqueue_remote({
        "idempotency_key": idempotency_key,
        "trace_id": idempotency_key,
        "requester_program_id": "workflow_automation_watchdog",
        "target_program_id": "workflow_source_discovery",
        "capability": "source_discovery",
        "priority": priority,
        "input": {},
    }, store, registry, precondition=precondition)
    task = result["task"]
    return {
        "created": result["created"],
        "task_id": task["task_id"],
        "status": task["status"],
        "idempotency_key": task["idempotency_key"],
    }


def enqueue_source_assessment_task(store, registry: dict, adapters: dict, *,
                                   idempotency_key: str, input_payload: dict,
                                   priority: int = 60, root: Path = ROOT,
                                   recovery_of_task_id: str | None = None) -> dict:
    """Enqueue one bounded assessment only from a successful discovery-producing Watchdog event."""
    if not isinstance(idempotency_key, str) or not idempotency_key.startswith("source-assessment:"):
        raise ValueError("source assessment requires a Watchdog-scoped idempotency key")
    if not isinstance(input_payload, dict):
        raise ValueError("source assessment input must be an object")
    predecessor = input_payload.get("predecessor")
    if not isinstance(predecessor, dict):
        raise ValueError("source assessment requires a typed predecessor artifact proof")
    expected_fields = {"program_id", "workflow_name", "workflow_run_id", "workflow_head_sha", "artifact_path", "artifact_sha256"}
    if set(predecessor) != expected_fields:
        raise ValueError("predecessor proof must contain exactly the reviewed discovery provenance fields")
    if predecessor.get("program_id") != "script_discover_sources":
        raise ValueError("source assessment predecessor must be script_discover_sources")
    if predecessor.get("workflow_name") != "Shadowrocket Source Discovery (Watchdog)":
        raise ValueError("source assessment predecessor workflow is not the reviewed production workflow")
    if not isinstance(predecessor.get("workflow_run_id"), str) or not predecessor["workflow_run_id"].isdigit():
        raise ValueError("predecessor workflow_run_id must be a decimal string")
    if not isinstance(predecessor.get("workflow_head_sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", predecessor["workflow_head_sha"]):
        raise ValueError("predecessor workflow_head_sha must be a full Git commit SHA")
    if predecessor.get("artifact_path") != "sources/discovered_sources.json":
        raise ValueError("source assessment predecessor artifact path is not allowlisted")
    if not isinstance(predecessor.get("artifact_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", predecessor["artifact_sha256"]):
        raise ValueError("predecessor artifact_sha256 must be a full SHA-256 digest")
    current = read_only_resource_digests(root, [predecessor["artifact_path"]]).get(predecessor["artifact_path"])
    if current is None or current != predecessor["artifact_sha256"]:
        raise ValueError("discovery predecessor artifact is missing or no longer matches its event snapshot")
    adapter = adapter_index(adapters).get("script_assess_sources")
    if not isinstance(adapter, dict) or adapter.get("enabled") is not True:
        raise ValueError("source assessment adapter is disabled")
    if adapter.get("adapter_type") != "python_cli" or adapter.get("interface_status") != "reviewed":
        raise ValueError("source assessment adapter interface is not reviewed")
    errors = validate_json_schema(input_payload, adapter.get("input_contract"))
    if errors:
        raise ValueError("source assessment input contract failed: " + "; ".join(errors[:5]))
    expected_key = f"source-assessment:{predecessor['workflow_run_id']}:parser-v2"
    recovery_one_key = expected_key + ":recovery:1"
    recovery_two_key = expected_key + ":recovery:2"
    artifact_recovery_key = expected_key + ":artifact-recovery:1"
    if idempotency_key not in {expected_key, recovery_one_key, recovery_two_key, artifact_recovery_key}:
        raise ValueError("source assessment idempotency key must be bound to its producer workflow run")
    precondition = None
    if idempotency_key == recovery_one_key:
        def require_dead_lettered_assessment(queue):
            base = next((item for item in queue.get("tasks", [])
                         if item.get("idempotency_key") == expected_key), None)
            if base is None or base.get("status") != "DEAD_LETTER":
                raise ValueError("source assessment recovery requires its exact base task to be DEAD_LETTER")
            base_predecessor = ((base.get("input") or {}).get("predecessor")
                                if isinstance(base.get("input"), dict) else None)
            if base_predecessor != predecessor:
                raise ValueError("source assessment recovery predecessor proof differs from the dead-lettered task")
            prior_recoveries = [
                item for item in queue.get("tasks", [])
                if isinstance(item.get("idempotency_key"), str)
                and item.get("idempotency_key").startswith(expected_key + ":recovery:")
            ]
            if prior_recoveries:
                raise ValueError("first source assessment recovery already exists for this Discovery run")
        precondition = require_dead_lettered_assessment
    elif idempotency_key == recovery_two_key:
        def require_timeout_corrected_recovery(queue):
            base = next((item for item in queue.get("tasks", [])
                         if item.get("idempotency_key") == expected_key), None)
            first = next((item for item in queue.get("tasks", [])
                          if item.get("idempotency_key") == recovery_one_key), None)
            if base is None or base.get("status") != "DEAD_LETTER":
                raise ValueError("second assessment recovery requires the exact base task to be DEAD_LETTER")
            if first is None or first.get("status") != "DEAD_LETTER":
                raise ValueError("second assessment recovery requires recovery:1 to be DEAD_LETTER")
            for prior in (base, first):
                prior_predecessor = ((prior.get("input") or {}).get("predecessor")
                                     if isinstance(prior.get("input"), dict) else None)
                if prior_predecessor != predecessor:
                    raise ValueError("assessment recovery predecessor proof differs from prior task evidence")
            prior_input = first.get("input") if isinstance(first.get("input"), dict) else {}
            prior_error = first.get("last_error") if isinstance(first.get("last_error"), dict) else {}
            if prior_error.get("type") != "execution_timeout" or prior_input.get("max_urls", 0) <= 4:
                raise ValueError("second assessment recovery is reserved for an oversized batch execution timeout")
            if input_payload.get("max_urls", 21) > 4:
                raise ValueError("second assessment recovery must use a batch of at most four URLs")
            if adapter.get("timeout_seconds", 0) < 300:
                raise ValueError("second assessment recovery requires the reviewed 300-second adapter budget")
            unexpected = [
                item for item in queue.get("tasks", [])
                if isinstance(item.get("idempotency_key"), str)
                and item.get("idempotency_key").startswith(expected_key + ":recovery:")
                and item.get("idempotency_key") not in {recovery_one_key, recovery_two_key}
            ]
            if unexpected:
                raise ValueError("unexpected assessment recovery task exists; refusing another retry")
        precondition = require_timeout_corrected_recovery
    elif idempotency_key == artifact_recovery_key:
        if not isinstance(recovery_of_task_id, str) or not re.fullmatch(r"task_[0-9a-f]{24}", recovery_of_task_id):
            raise ValueError("artifact recovery requires the exact verified Assessment task ID")
        def require_verified_assessment_for_artifact_recovery(queue):
            tasks = queue.get("tasks", [])
            prior = next((item for item in tasks
                          if isinstance(item, dict) and item.get("task_id") == recovery_of_task_id), None)
            if prior is None:
                raise ValueError("artifact recovery predecessor Assessment task ID is not present in the canonical queue")
            if (
                prior.get("target_program_id") != "script_assess_sources"
                or prior.get("requester_program_id") != "workflow_automation_watchdog"
            ):
                raise ValueError("artifact recovery source task is not a Watchdog-owned Assessment")
            prior_key = prior.get("idempotency_key")
            if not isinstance(prior_key, str) or not prior_key.startswith("source-assessment:"):
                raise ValueError("artifact recovery source task is not in the source-assessment idempotency namespace")
            prior_input = prior.get("input") if isinstance(prior.get("input"), dict) else {}
            if prior_input.get("predecessor") != predecessor:
                raise ValueError("artifact recovery predecessor proof differs from the selected Assessment task")
            if prior.get("status") != "SUCCEEDED" or (prior.get("verification") or {}).get("status") != "passed":
                raise ValueError("artifact recovery requires the exact prior Assessment task to be independently verified SUCCEEDED")
            verification = (prior.get("result") or {}).get("artifact_verification") or {}
            if verification.get("valid") is not True or verification.get("activation_count") != 0:
                raise ValueError("artifact recovery requires a valid non-activating Assessment result")
            active = [
                item for item in tasks
                if isinstance(item, dict)
                and item.get("task_id") != recovery_of_task_id
                and item.get("target_program_id") == "script_assess_sources"
                and ((item.get("input") or {}).get("predecessor") if isinstance(item.get("input"), dict) else None) == predecessor
                and item.get("status") in {"QUEUED", "CLAIMED", "VERIFYING"}
            ]
            if active:
                raise ValueError("artifact recovery is blocked while another Assessment task for this Discovery run is active")
            if input_payload.get("max_urls", 21) > 4 or adapter.get("timeout_seconds", 0) < 300:
                raise ValueError("artifact recovery must use at most four URLs and the reviewed 300-second budget")
            if any(
                isinstance(item.get("idempotency_key"), str)
                and item.get("idempotency_key") == artifact_recovery_key
                for item in tasks
            ):
                raise ValueError("Assessment artifact recovery already exists for this Discovery run")
        precondition = require_verified_assessment_for_artifact_recovery
    elif recovery_of_task_id is not None:
        raise ValueError("--recovery-of-task-id is valid only for artifact-recovery Assessment tasks")
    result = enqueue_remote({
        "idempotency_key": idempotency_key,
        "trace_id": f"discovery-run:{predecessor['workflow_run_id']}:{predecessor['workflow_head_sha'][:12]}",
        "requester_program_id": "workflow_automation_watchdog",
        "target_program_id": "script_assess_sources",
        "capability": "source_assessment",
        "priority": priority,
        "input": input_payload,
    }, store, registry, precondition=precondition)
    task = result["task"]
    return {
        "created": result["created"],
        "task_id": task["task_id"],
        "status": task["status"],
        "idempotency_key": task["idempotency_key"],
        "predecessor_artifact_sha256": predecessor["artifact_sha256"],
        "predecessor_workflow_run_id": predecessor["workflow_run_id"],
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


def filter_eligible_task_ids(eligible_task_ids: set[str], task_id: str | None = None) -> set[str]:
    if not isinstance(eligible_task_ids,set):
        raise ValueError("eligible task IDs must be a set")
    if task_id is None:
        return set(eligible_task_ids)
    if not isinstance(task_id,str) or not task_id.strip():
        raise ValueError("task_id filter must be a non-empty string")
    return eligible_task_ids.intersection({task_id})


def production_dispatch_mode(root: Path = ROOT) -> str:
    """Fail closed unless the repository explicitly enables production dispatch."""
    path = Path(root) / "automation" / "production_control.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "hold"
    if (not isinstance(document, dict) or document.get("schema_version") != 1
            or document.get("dispatch_mode") not in {"enabled", "hold"}):
        return "hold"
    return document["dispatch_mode"]


def summarize_active_tasks(queue: dict) -> list[dict]:
    """Return safe queue diagnostics for active work without exposing lease tokens."""
    if not isinstance(queue, dict) or not isinstance(queue.get("tasks"), list):
        raise ValueError("task queue must contain a tasks array")
    summaries = []
    for task in queue["tasks"]:
        if not isinstance(task, dict) or task.get("status") not in {"QUEUED", "CLAIMED", "VERIFYING"}:
            continue
        payload = task.get("input") if isinstance(task.get("input"), dict) else {}
        intent = task.get("dispatch_intent") if isinstance(task.get("dispatch_intent"), dict) else {}
        lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
        resource_lease = task.get("resource_lease") if isinstance(task.get("resource_lease"), dict) else {}
        resource_rows = []
        resources = resource_lease.get("resources") if isinstance(resource_lease.get("resources"), dict) else {}
        for key, proof in sorted(resources.items()):
            if not isinstance(proof, dict):
                continue
            resource_rows.append({
                "resource": key,
                "fencing_token": proof.get("fencing_token"),
                "lease_id": proof.get("lease_id"),
            })
        evidence = task.get("result", {}).get("run_evidence", {}) if isinstance(task.get("result"), dict) else {}
        summaries.append({
            "task_id": task.get("task_id"),
            "target_program_id": task.get("target_program_id"),
            "status": task.get("status"),
            "attempts": task.get("attempts"),
            "max_attempts": task.get("max_attempts"),
            "production_fingerprint": payload.get("production_fingerprint"),
            "production_decision": payload.get("production_decision"),
            "idempotency_key": task.get("idempotency_key"),
            "dispatch_intent": {
                "workflow_path": intent.get("workflow_path"),
                "correlation_id": intent.get("correlation_id"),
                "dispatch_attempt": intent.get("dispatch_attempt"),
                "requested_head_sha": intent.get("requested_head_sha"),
            } if intent else None,
            "scheduler_lease": {
                "owner": lease.get("owner"),
                "expires_at": lease.get("expires_at"),
            } if lease else None,
            "resource_lease": {
                "status": resource_lease.get("status"),
                "expires_at": resource_lease.get("expires_at"),
                "resources": resource_rows,
            } if resource_lease else None,
            "run_evidence": {
                "run_id": evidence.get("run_id"),
                "status": evidence.get("status"),
            } if evidence else None,
        })
    return sorted(summaries, key=lambda item: (str(item.get("target_program_id")), str(item.get("task_id"))))


def run_scheduler_once(store, registry: dict, adapters: dict, *,
                       worker_id: str, max_tasks: int = 1, task_id: str | None = None,
                       root: Path = ROOT, now: datetime | None = None,
                       verify_only: bool = False) -> dict:
    if not isinstance(max_tasks, int) or isinstance(max_tasks, bool) or not 1 <= max_tasks <= 10:
        raise ValueError("max_tasks must be an integer from 1 to 10")
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    if task_id is not None and (not isinstance(task_id,str) or not task_id.strip()):
        raise ValueError("task_id filter must be a non-empty string")
    if not isinstance(verify_only, bool):
        raise ValueError("verify_only must be a boolean")
    fixed_now = now
    initial_now = now or now_utc()
    dispatch_mode = production_dispatch_mode(root)
    if dispatch_mode != "enabled":
        snapshot = store.read().document
        validate_candidate(snapshot, registry)
        return {
            "dispatch_mode": "hold",
            "processed_count": 0,
            "processed": [],
            "blocked": [],
            "initial_verification": {"verified_count": 0, "deferred_count": 0, "held": True},
            "recovered_count": 0,
            "queue_revision": snapshot["revision"],
        }
    recovered = recover_remote(store, registry, initial_now)
    initial_verification = verify_pending_remote(store, registry, adapters, initial_now)
    superseded_stale_tasks = supersede_stale_queued_production_tasks(store, registry, root)
    if verify_only:
        final_snapshot = store.read().document
        validate_candidate(final_snapshot, registry)
        active_tasks = summarize_active_tasks(final_snapshot)
        active_fingerprints = sorted({
            item["production_fingerprint"]
            for item in active_tasks
            if item.get("target_program_id") == "workflow_auto_sync"
            and (
                item.get("status") in {"CLAIMED", "VERIFYING"}
                or (item.get("status") == "QUEUED" and isinstance(item.get("dispatch_intent"), dict))
            )
            and isinstance(item.get("production_fingerprint"), str)
        })
        return {
            "verification_only": True,
            "processed_count": 0,
            "processed": [],
            "blocked": [],
            "initial_verification": initial_verification,
            "recovered_count": len(recovered),
            "superseded_stale_production_task_ids": superseded_stale_tasks,
            "queue_revision": final_snapshot["revision"],
            "active_task_summaries": active_tasks,
            "active_production_fingerprints": active_fingerprints,
        }
    processed = []
    blocked_seen = {}

    for _ in range(max_tasks):
        snapshot = store.read().document
        iteration_now = fixed_now or now_utc()
        plan = build_execution_plan(snapshot, registry, adapters, root, iteration_now)
        for item in plan["blocked"]:
            blocked_seen[item["task_id"]] = item["reason"]
        eligible = set(plan["eligible_task_ids"])
        eligible = filter_eligible_task_ids(eligible, task_id)
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
            # The plan is only a snapshot: a resource lease may be acquired by
            # another worker between planning and claim. Re-reading the same
            # eligible set cannot resolve that conflict and would spin forever.
            # Leave the task queued and let the next Watchdog reconciliation retry.
            break
        adapter = adapter_index(adapters)[task["target_program_id"]]
        processed.append(execute_claimed_task(task, adapter, store, registry, adapters, root, now))

    final_snapshot = store.read().document
    validate_candidate(final_snapshot, registry)
    active_tasks = summarize_active_tasks(final_snapshot)
    active_fingerprints = sorted({
        item["production_fingerprint"]
        for item in active_tasks
        if item.get("target_program_id") == "workflow_auto_sync"
        and (
            item.get("status") in {"CLAIMED", "VERIFYING"}
            or (item.get("status") == "QUEUED" and isinstance(item.get("dispatch_intent"), dict))
        )
        and isinstance(item.get("production_fingerprint"), str)
    })
    return {
        "processed_count": len(processed),
        "processed": processed,
        "blocked": [{"task_id": key, "reason": value} for key, value in sorted(blocked_seen.items())],
        "initial_verification": initial_verification,
        "recovered_count": len(recovered),
        "superseded_stale_production_task_ids": superseded_stale_tasks,
        "queue_revision": final_snapshot["revision"],
        "active_task_summaries": active_tasks,
        "active_production_fingerprints": active_fingerprints,
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
    parser.add_argument("--task-id", help="Run only this eligible durable task ID")
    parser.add_argument("--verify-only", action="store_true", help="Recover and verify pending tasks without claiming or dispatching any task")
    parser.add_argument("--token-stdin", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--recovery-of-task-id", help="Exact verified Assessment task being used as the artifact-recovery proof")
    parser.add_argument("--priority", type=int, default=80)
    parser.add_argument("--input-json", default="{}")
    parser.add_argument("--current-main-sha", help="Current main commit used to resolve superseded terminal tasks")
    parser.add_argument("command", choices=["plan", "run-once", "enqueue-auto-sync", "enqueue-source-discovery", "enqueue-source-assessment", "resolve-superseded-dead-letters"])
    args = parser.parse_args()
    try:
        if args.verify_only and args.command != "run-once":
            raise ValueError("--verify-only is valid only with run-once")
        token = sys.stdin.read().strip() if args.token_stdin else None
        if args.command in {"run-once", "enqueue-auto-sync", "enqueue-source-discovery", "enqueue-source-assessment", "resolve-superseded-dead-letters"} and not token:
            raise ValueError(f"{args.command} requires a queue token supplied through --token-stdin")
        store = make_store(args.repository, args.branch, args.queue_path, token=token)
        registry = load_object(args.registry, "program registry")
        adapters = load_object(args.adapters, "execution adapter inventory")
        if args.command == "plan":
            plan = build_execution_plan(store.read().document, registry, adapters)
            print(json.dumps(plan, ensure_ascii=False))
        elif args.command == "enqueue-source-discovery":
            print(json.dumps(enqueue_source_discovery_task(
                store, registry, idempotency_key=args.idempotency_key,
                priority=args.priority,
            ), ensure_ascii=False))
        elif args.command == "enqueue-source-assessment":
            if not isinstance(args.idempotency_key, str) or not args.idempotency_key:
                raise ValueError("enqueue-source-assessment requires --idempotency-key")
            if not 0 <= args.priority <= 100:
                raise ValueError("--priority must be an integer from 0 to 100")
            try:
                input_payload = json.loads(args.input_json)
            except json.JSONDecodeError as exc:
                raise ValueError(f"--input-json is invalid JSON: {exc}") from exc
            print(json.dumps(enqueue_source_assessment_task(
                store, registry, adapters, idempotency_key=args.idempotency_key,
                priority=args.priority, input_payload=input_payload,
                recovery_of_task_id=args.recovery_of_task_id,
            ), ensure_ascii=False))
        elif args.command == "resolve-superseded-dead-letters":
            if not args.current_main_sha:
                raise ValueError("resolve-superseded-dead-letters requires --current-main-sha")
            resolved = resolve_superseded_dead_letters(
                store, registry, current_main_sha=args.current_main_sha,
            )
            print(json.dumps({"resolved_count": len(resolved), "tasks": resolved}, ensure_ascii=False))
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
                max_tasks=args.max_tasks, task_id=args.task_id,
                verify_only=args.verify_only,
            ), ensure_ascii=False))
        return 0
    except (ValueError, OSError, QueueStoreError, ProtectedConfigMutationError) as exc:
        print(f"SCHEDULER ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
