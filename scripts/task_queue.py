#!/usr/bin/env python3
"""Validate the durable cross-program task envelope and queue without dispatching work."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()


import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = Path("automation/task_queue.json")
REGISTRY_PATH = Path("automation/program_registry.json")
TASK_ID_RE = re.compile(r"^task_[0-9a-f]{24}$")
STATUSES = {"QUEUED", "CLAIMED", "VERIFYING", "SUCCEEDED", "FAILED", "CANCELLED", "DEAD_LETTER"}
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "DEAD_LETTER"}


def parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def validate_task_queue(root: Path = ROOT, queue_path: Path | None = None, registry_path: Path | None = None) -> dict:
    queue_path = queue_path or (root / QUEUE_PATH)
    registry_path = registry_path or (root / REGISTRY_PATH)
    queue = load_json(queue_path, "task queue")
    registry = load_json(registry_path, "program registry")
    if queue.get("schema_version") != 1:
        raise ValueError("task queue schema_version must be 1")
    revision = queue.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("task queue revision must be a non-negative integer")
    tasks = queue.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("task queue tasks must be an array")
    programs = registry.get("programs")
    if not isinstance(programs, list):
        raise ValueError("program registry programs must be an array")
    by_id = {item.get("id"): item for item in programs if isinstance(item, dict) and isinstance(item.get("id"), str)}
    task_ids: set[str] = set()
    idempotency_keys: set[str] = set()

    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("each task must be an object")
        required = {
            "task_id", "idempotency_key", "trace_id", "requester_program_id",
            "target_program_id", "capability", "created_at", "not_before",
            "priority", "status", "attempts", "max_attempts", "input",
            "lease", "result", "last_error", "state_history",
        }
        missing = sorted(required - set(task))
        if missing:
            raise ValueError("task is missing required fields: " + ", ".join(missing))
        task_id = task["task_id"]
        if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
            raise ValueError("task_id must match task_ followed by 24 lowercase hex characters")
        if task_id in task_ids:
            raise ValueError(f"duplicate task_id: {task_id}")
        task_ids.add(task_id)
        execution_backend = task.get("execution_backend")
        if execution_backend is not None and execution_backend != "github_contents":
            raise ValueError(f"{task_id}.execution_backend is unsupported")
        idem = task["idempotency_key"]
        if not isinstance(idem, str) or not 1 <= len(idem) <= 200:
            raise ValueError(f"{task_id}.idempotency_key must contain 1 to 200 characters")
        if idem in idempotency_keys:
            raise ValueError(f"duplicate idempotency_key: {idem}")
        idempotency_keys.add(idem)
        trace = task["trace_id"]
        if not isinstance(trace, str) or not trace.strip():
            raise ValueError(f"{task_id}.trace_id is required")
        requester, target = task["requester_program_id"], task["target_program_id"]
        if not isinstance(requester, str) or not isinstance(target, str):
            raise ValueError(f"{task_id} requester and target IDs must be strings")
        if requester not in by_id:
            raise ValueError(f"{task_id} references unknown requester program: {requester}")
        if target not in by_id:
            raise ValueError(f"{task_id} references unknown target program: {target}")
        target_program = by_id[target]
        if not isinstance(task["capability"], str) or not task["capability"]:
            raise ValueError(f"{task_id}.capability must be a non-empty string")
        if task["capability"] not in target_program.get("capabilities", []):
            raise ValueError(f"{task_id} requests a capability not declared by {target}")
        orchestration = target_program.get("orchestration", {})
        parse_utc(task["created_at"], f"{task_id}.created_at")
        parse_utc(task["not_before"], f"{task_id}.not_before")
        priority = task["priority"]
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
            raise ValueError(f"{task_id}.priority must be an integer from 0 to 100")
        status = task["status"]
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError(f"{task_id} has unsupported status: {status}")
        attempts, max_attempts = task["attempts"], task["max_attempts"]
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            raise ValueError(f"{task_id}.attempts must be a non-negative integer")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 0 <= max_attempts <= 5:
            raise ValueError(f"{task_id}.max_attempts must be an integer from 0 to 5")
        if attempts > max_attempts:
            raise ValueError(f"{task_id} attempts exceed its stored retry budget")
        active_or_retryable = status in {"QUEUED", "CLAIMED", "VERIFYING"} or (status == "FAILED" and attempts < max_attempts)
        if active_or_retryable:
            if orchestration.get("enabled") is not True:
                raise ValueError(f"{task_id} target program is not enabled for orchestration: {target}")
            if requester not in orchestration.get("allowed_callers", []):
                raise ValueError(f"{task_id} requester is not allowed to call {target}: {requester}")
            if max_attempts > orchestration.get("max_attempts", -1):
                raise ValueError(f"{task_id} attempts exceed the registered retry budget")
        timeout = orchestration.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
            raise ValueError(f"{task_id} target has no valid registered timeout")
        if not isinstance(task["input"], dict):
            raise ValueError(f"{task_id}.input must be an object")
        lease = task["lease"]
        history = task["state_history"]
        if not isinstance(history, list) or not history or any(state not in STATUSES for state in history):
            raise ValueError(f"{task_id}.state_history must be a non-empty array of valid statuses")
        if history[-1] != status:
            raise ValueError(f"{task_id}.state_history must end with the current status")
        allowed_transitions = {
            "QUEUED": {"CLAIMED", "CANCELLED", "VERIFYING"},
            "CLAIMED": {"VERIFYING", "SUCCEEDED", "FAILED", "QUEUED", "DEAD_LETTER"},
            "VERIFYING": {"SUCCEEDED", "FAILED", "QUEUED", "DEAD_LETTER"},
            "FAILED": {"QUEUED", "DEAD_LETTER", "CANCELLED"},
            "SUCCEEDED": set(),
            "CANCELLED": set(),
            "DEAD_LETTER": {"VERIFYING"},
        }
        for previous, current in zip(history, history[1:]):
            if current not in allowed_transitions[previous]:
                raise ValueError(f"{task_id}.state_history contains illegal transition {previous} -> {current}")
        if status == "CLAIMED":
            if not isinstance(lease, dict) or not isinstance(lease.get("owner"), str) or not lease["owner"].strip():
                raise ValueError(f"{task_id} CLAIMED task requires a lease owner")
            if not isinstance(lease.get("token"), str) or not lease["token"]:
                raise ValueError(f"{task_id} CLAIMED task requires a lease token")
            parse_utc(lease.get("expires_at"), f"{task_id}.lease.expires_at")
        elif lease is not None:
            raise ValueError(f"{task_id} must not retain a lease while status is {status}")
        if any(previous == "QUEUED" and current == "VERIFYING" for previous, current in zip(history, history[1:])):
            if not isinstance(task.get("dispatch_intent"), dict):
                raise ValueError(f"{task_id} may enter VERIFYING from QUEUED only through a persisted workflow dispatch intent")
        if any(previous == "DEAD_LETTER" and current == "VERIFYING" for previous, current in zip(history, history[1:])):
            if not isinstance(task.get("dispatch_intent"), dict):
                raise ValueError(f"{task_id} may leave DEAD_LETTER for VERIFYING only to reconcile a persisted workflow dispatch intent")
        dispatch_intent = task.get("dispatch_intent")
        if dispatch_intent is not None:
            if not isinstance(dispatch_intent, dict):
                raise ValueError(f"{task_id}.dispatch_intent must be an object")
            workflow_id = dispatch_intent.get("workflow_id")
            if isinstance(workflow_id, bool) or not isinstance(workflow_id, int) or workflow_id < 1:
                raise ValueError(f"{task_id}.dispatch_intent.workflow_id must be a positive integer")
            if dispatch_intent.get("task_id") != task_id:
                raise ValueError(f"{task_id}.dispatch_intent task ID mismatch")
            dispatch_attempt = dispatch_intent.get("dispatch_attempt")
            if isinstance(dispatch_attempt, bool) or not isinstance(dispatch_attempt, int) or dispatch_attempt < 1 or dispatch_attempt > attempts:
                raise ValueError(f"{task_id}.dispatch_intent dispatch attempt is invalid")
            expected_correlation = f"{task_id}-a{dispatch_attempt}"
            if dispatch_intent.get("correlation_id") != expected_correlation or dispatch_intent.get("correlation_title") != f"Automation task {expected_correlation}":
                raise ValueError(f"{task_id}.dispatch_intent correlation identity mismatch")
            if not isinstance(dispatch_intent.get("workflow_path"), str) or not dispatch_intent["workflow_path"].startswith(".github/workflows/"):
                raise ValueError(f"{task_id}.dispatch_intent workflow path is invalid")
            if not isinstance(dispatch_intent.get("ref"), str) or not dispatch_intent["ref"]:
                raise ValueError(f"{task_id}.dispatch_intent ref is required")
            if not isinstance(dispatch_intent.get("requested_head_sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", dispatch_intent["requested_head_sha"]):
                raise ValueError(f"{task_id}.dispatch_intent head SHA is invalid")
            parse_utc(dispatch_intent.get("prepared_at"), f"{task_id}.dispatch_intent.prepared_at")
        result = task["result"]
        if status in {"VERIFYING", "SUCCEEDED"} and not isinstance(result, dict):
            raise ValueError(f"{task_id} {status} task requires a result object")
        if result is not None and not isinstance(result, dict):
            raise ValueError(f"{task_id}.result must be an object or null")
        error = task["last_error"]
        if error is not None and not isinstance(error, dict):
            raise ValueError(f"{task_id}.last_error must be an object or null")
        verification = task.get("verification")
        if verification is not None:
            if not isinstance(verification, dict):
                raise ValueError(f"{task_id}.verification must be an object or null")
            if verification.get("verifier_program_id") not in by_id:
                raise ValueError(f"{task_id}.verification references an unknown verifier program")
            if verification.get("status") not in {"passed", "failed"}:
                raise ValueError(f"{task_id}.verification.status must be passed or failed")
            parse_utc(verification.get("verified_at"), f"{task_id}.verification.verified_at")
            if not isinstance(verification.get("contract_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", verification["contract_sha256"]):
                raise ValueError(f"{task_id}.verification.contract_sha256 must be a SHA-256 digest")
            if status == "VERIFYING":
                raise ValueError(f"{task_id} VERIFYING task must not retain a previous verification")
            if status == "SUCCEEDED" and verification["status"] != "passed":
                raise ValueError(f"{task_id} SUCCEEDED task requires passed verification")
        if execution_backend == "github_contents" and status == "SUCCEEDED":
            if not isinstance(verification, dict) or verification.get("status") != "passed":
                raise ValueError(f"{task_id} GitHub-backed SUCCEEDED task requires independent verification")

    manual_authorizations = queue.get("manual_authorizations", {})
    if not isinstance(manual_authorizations, dict):
        raise ValueError("manual_authorizations must be an object")
    task_by_id = {item["task_id"]: item for item in tasks if isinstance(item, dict) and isinstance(item.get("task_id"), str)}
    consumed_task_ids: set[str] = set()
    for run_id, record in manual_authorizations.items():
        if not isinstance(run_id, str) or not run_id.isdigit() or not isinstance(record, dict):
            raise ValueError("manual authorization ledger key/record is invalid")
        required_record_fields = {
            "task_id", "run_id", "run_attempt", "actor_id", "repository",
            "workflow_ref", "event", "ref", "head_sha", "requester_program_id",
            "target_program_id", "capability", "idempotency_key",
            "production_fingerprint", "scope_sha256", "consumed_at",
        }
        if required_record_fields - set(record):
            raise ValueError("manual authorization consumption record is incomplete")
        task_id = record.get("task_id")
        if not isinstance(task_id, str) or task_id not in task_by_id or task_id in consumed_task_ids:
            raise ValueError("manual authorization must consume one unique existing task")
        consumed_task_ids.add(task_id)
        task = task_by_id[task_id]
        payload = task.get("input")
        if not isinstance(payload, dict) or payload.get("production_decision") != "USER_AUTHORIZED_MANUAL_AUDIT":
            raise ValueError("manual authorization record must reference a manually authorized task")
        expected = {
            "run_id": payload.get("authorization_run_id"),
            "run_attempt": payload.get("authorization_run_attempt"),
            "actor_id": payload.get("authorization_actor_id"),
            "repository": payload.get("authorization_repository"),
            "workflow_ref": payload.get("authorization_workflow_ref"),
            "event": payload.get("authorization_event"),
            "ref": payload.get("authorization_ref"),
            "head_sha": payload.get("authorization_head_sha"),
            "requester_program_id": task.get("requester_program_id"),
            "target_program_id": task.get("target_program_id"),
            "capability": task.get("capability"),
            "idempotency_key": task.get("idempotency_key"),
            "production_fingerprint": payload.get("production_fingerprint"),
        }
        if run_id != payload.get("authorization_run_id") or record.get("task_id") != task_id:
            raise ValueError("manual authorization run/task binding is invalid")
        if any(record.get(field) != value for field, value in expected.items()):
            raise ValueError("manual authorization consumption record does not match its task scope")
        if (task.get("requester_program_id") != "workflow_automation_watchdog"
                or task.get("target_program_id") != "workflow_auto_sync"
                or task.get("capability") != "deterministic_audit"
                or payload.get("authorization_target_program_id") != task.get("target_program_id")
                or payload.get("authorization_idempotency_key") != task.get("idempotency_key")
                or payload.get("authorization_requested") is not True
                or payload.get("baseline_source_event") != payload.get("authorization_event")
                or payload.get("baseline_source_sha") != payload.get("authorization_head_sha")):
            raise ValueError("manual authorization task target/idempotency binding is invalid")
        if not isinstance(record.get("scope_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["scope_sha256"]):
            raise ValueError("manual authorization scope digest is invalid")
        scope = {
            "repository": payload["authorization_repository"],
            "workflow_ref": payload["authorization_workflow_ref"],
            "event": payload["authorization_event"],
            "actor": payload["authorization_actor"],
            "actor_id": payload["authorization_actor_id"],
            "run_id": payload["authorization_run_id"],
            "run_attempt": payload["authorization_run_attempt"],
            "ref": payload["authorization_ref"],
            "head_sha": payload["authorization_head_sha"],
            "requester_program_id": task["requester_program_id"],
            "target_program_id": task["target_program_id"],
            "capability": task["capability"],
            "idempotency_key": task["idempotency_key"],
            "production_fingerprint": payload["production_fingerprint"],
        }
        expected_scope_sha = hashlib.sha256(
            json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if record["scope_sha256"] != expected_scope_sha:
            raise ValueError("manual authorization scope digest does not match its persisted task")
        if (not isinstance(record.get("run_attempt"), str) or not record["run_attempt"].isdigit()
                or not isinstance(record.get("actor_id"), str) or not record["actor_id"].isdigit()
                or record.get("event") != "workflow_dispatch"
                or record.get("ref") != "refs/heads/main"
                or not isinstance(record.get("repository"), str) or not record["repository"].strip()
                or record.get("workflow_ref") != f'{record["repository"]}/.github/workflows/automation-watchdog.yml@refs/heads/main'
                or not isinstance(record.get("head_sha"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", record["head_sha"])):
            raise ValueError("manual authorization trusted workflow identity is invalid")
        parse_utc(record.get("consumed_at"), f"manual_authorizations.{run_id}.consumed_at")
    for task in tasks:
        payload = task.get("input") if isinstance(task, dict) else None
        if isinstance(payload, dict) and payload.get("production_decision") == "USER_AUTHORIZED_MANUAL_AUDIT":
            run_id = payload.get("authorization_run_id")
            record = manual_authorizations.get(run_id) if isinstance(run_id, str) else None
            if not isinstance(record, dict) or record.get("task_id") != task.get("task_id"):
                raise ValueError("manually authorized task lacks its durable one-shot consumption record")

    resource_leases = queue.get("resource_leases", {})
    if not isinstance(resource_leases, dict):
        raise ValueError("resource_leases must be an object")
    for resource, record in resource_leases.items():
        if (not isinstance(resource, str) or not resource or resource.startswith("/")
                or chr(92) in resource or any(part in {"", ".", ".."} for part in resource.split("/"))):
            raise ValueError(f"resource lease key is not a canonical relative path: {resource!r}")
        if not isinstance(record, dict) or record.get("status") not in {"ACTIVE", "RELEASED"}:
            raise ValueError(f"resource lease record is invalid: {resource}")
        for field in ("task_id", "worker_id", "task_lease_token", "lease_id"):
            if not isinstance(record.get(field), str) or not record[field]:
                raise ValueError(f"resource lease {resource}.{field} is required")
        fence = record.get("fencing_token")
        if isinstance(fence, bool) or not isinstance(fence, int) or fence < 1:
            raise ValueError(f"resource lease {resource}.fencing_token is invalid")
        for field in ("acquired_at", "renewed_at", "expires_at"):
            parse_utc(record.get(field), f"resource_leases.{resource}.{field}")
        if record.get("status") == "ACTIVE" and record.get("released_at") is not None:
            raise ValueError(f"active resource lease {resource} cannot have released_at")
        if record.get("status") == "RELEASED":
            parse_utc(record.get("released_at"), f"resource_leases.{resource}.released_at")

    for task in tasks:
        resource_lease = task.get("resource_lease")
        if resource_lease is None:
            continue
        task_id = task["task_id"]
        if not isinstance(resource_lease, dict) or resource_lease.get("status") not in {"ACTIVE", "RELEASED", "LOST"}:
            raise ValueError(f"{task_id}.resource_lease is invalid")
        seconds = resource_lease.get("lease_seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 21600:
            raise ValueError(f"{task_id}.resource_lease.lease_seconds is invalid")
        resources = resource_lease.get("resources")
        if not isinstance(resources, dict) or not resources:
            raise ValueError(f"{task_id}.resource_lease.resources must be a non-empty object")
        for resource, proof in resources.items():
            if resource not in resource_leases or not isinstance(proof, dict):
                raise ValueError(f"{task_id}.resource_lease references an unknown resource")
            lease_id, fence = proof.get("lease_id"), proof.get("fencing_token")
            if not isinstance(lease_id, str) or not lease_id or isinstance(fence, bool) or not isinstance(fence, int) or fence < 1:
                raise ValueError(f"{task_id}.resource_lease proof is invalid for {resource}")
            if resource_lease["status"] == "ACTIVE":
                current = resource_leases[resource]
                if current.get("status") != "ACTIVE" or current.get("task_id") != task_id or current.get("lease_id") != lease_id or current.get("fencing_token") != fence:
                    raise ValueError(f"{task_id}.resource_lease is stale for {resource}")
        if resource_lease.get("status") == "ACTIVE":
            parse_utc(resource_lease.get("expires_at"), f"{task_id}.resource_lease.expires_at")
        elif resource_lease.get("status") == "LOST":
            parse_utc(resource_lease.get("lost_at"), f"{task_id}.resource_lease.lost_at")

    return {"valid": True, "task_count": len(tasks), "revision": revision}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    try:
        result = validate_task_queue(args.root, args.queue, args.registry)
    except ValueError as exc:
        print(f"TASK QUEUE INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
