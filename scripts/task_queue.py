#!/usr/bin/env python3
"""Validate the durable cross-program task envelope and queue without dispatching work."""
from __future__ import annotations

import argparse
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
        if orchestration.get("enabled") is not True:
            raise ValueError(f"{task_id} target program is not enabled for orchestration: {target}")
        if requester not in orchestration.get("allowed_callers", []):
            raise ValueError(f"{task_id} requester is not allowed to call {target}: {requester}")
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
        if attempts > max_attempts or max_attempts > orchestration.get("max_attempts", -1):
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
            "QUEUED": {"CLAIMED", "CANCELLED"},
            "CLAIMED": {"VERIFYING", "SUCCEEDED", "FAILED", "QUEUED", "DEAD_LETTER"},
            "VERIFYING": {"SUCCEEDED", "FAILED", "QUEUED", "DEAD_LETTER"},
            "FAILED": {"QUEUED", "DEAD_LETTER", "CANCELLED"},
            "SUCCEEDED": set(),
            "CANCELLED": set(),
            "DEAD_LETTER": set(),
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
        result = task["result"]
        if status in {"VERIFYING", "SUCCEEDED"} and not isinstance(result, dict):
            raise ValueError(f"{task_id} {status} task requires a result object")
        if result is not None and not isinstance(result, dict):
            raise ValueError(f"{task_id}.result must be an object or null")
        error = task["last_error"]
        if error is not None and not isinstance(error, dict):
            raise ValueError(f"{task_id}.last_error must be an object or null")

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
