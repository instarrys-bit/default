#!/usr/bin/env python3
"""GitHub-backed task queue runtime using SHA-CAS for every state mutation."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from github_queue_store import GitHubContentsQueueStore, QueueStoreError
from task_queue_runtime import authorize, now_utc, stamp
from task_queue import validate_task_queue


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "automation" / "program_registry.json"


def load_registry(path: Path = REGISTRY) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read program registry: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("programs"), list):
        raise ValueError("program registry is invalid")
    return value


def validate_envelope(queue: dict) -> None:
    if (not isinstance(queue, dict) or queue.get("schema_version") != 1
            or isinstance(queue.get("revision"), bool)
            or not isinstance(queue.get("revision"), int) or queue["revision"] < 0
            or not isinstance(queue.get("tasks"), list)):
        raise ValueError("remote task queue envelope is invalid")


def validate_candidate(queue: dict, registry: dict) -> None:
    """Run the independent queue integrity validator before accepting a mutation."""
    with tempfile.TemporaryDirectory(prefix="remote-queue-verify-") as directory:
        root = Path(directory)
        queue_path = root / "task_queue.json"
        registry_path = root / "program_registry.json"
        queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
        registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
        validate_task_queue(root=root, queue_path=queue_path, registry_path=registry_path)


def make_store(repository: str | None = None, branch: str | None = None,
               path: str = "automation/task_queue.json") -> GitHubContentsQueueStore:
    repository = repository or os.environ.get("GITHUB_REPOSITORY", "")
    branch = branch or os.environ.get("GITHUB_REF_NAME", "main")
    if not repository:
        raise ValueError("repository is required (or set GITHUB_REPOSITORY)")
    return GitHubContentsQueueStore(repository, path, branch=branch)


def enqueue_remote(task: dict, store: GitHubContentsQueueStore,
                   registry: dict, now: datetime | None = None) -> dict:
    if not isinstance(task, dict):
        raise ValueError("task payload must be an object")
    now = now or now_utc()
    programs = registry["programs"]
    by_id = {p.get("id"): p for p in programs if isinstance(p, dict)}
    policy = authorize(task, by_id)
    idem = task.get("idempotency_key")
    if not isinstance(idem, str) or not 1 <= len(idem) <= 200:
        raise ValueError("idempotency_key must contain 1 to 200 characters")
    priority = task.get("priority", 50)
    payload = task.get("input", {})
    if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 100:
        raise ValueError("priority must be an integer from 0 to 100")
    if not isinstance(payload, dict):
        raise ValueError("input must be an object")

    task_id = "task_" + uuid.uuid4().hex[:24]
    trace_id = str(task.get("trace_id") or uuid.uuid4().hex)

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        for old in queue["tasks"]:
            if old.get("idempotency_key") == idem:
                fields = ("requester_program_id", "target_program_id", "capability", "priority", "input")
                if any(old.get(k) != task.get(k, 50 if k == "priority" else {}) for k in fields):
                    raise ValueError("idempotency_key is already used for a different task payload")
                validate_candidate(queue, registry)
                return queue, {"created": False, "task": old}
        item = {
            "task_id": task_id,
            "execution_backend": "github_contents",
            "idempotency_key": idem,
            "trace_id": trace_id,
            "requester_program_id": task["requester_program_id"],
            "target_program_id": task["target_program_id"],
            "capability": task["capability"],
            "created_at": stamp(now), "not_before": stamp(now),
            "priority": priority, "status": "QUEUED", "attempts": 0,
            "max_attempts": policy["max_attempts"], "input": payload,
            "lease": None, "result": None, "last_error": None,
            "state_history": ["QUEUED"],
        }
        queue["tasks"].append(item)
        queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, {"created": True, "task": item}
    return store.mutate(mutate)


def claim_remote(worker_id: str, store: GitHubContentsQueueStore,
                 registry: dict, *, eligible_task_ids: set[str],
                 now: datetime | None = None) -> dict | None:
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    if not isinstance(eligible_task_ids, set) or any(not isinstance(item, str) for item in eligible_task_ids):
        raise ValueError("eligible_task_ids must be a set of task IDs supplied by the reviewed scheduler")
    now = now or now_utc()
    by_id = {p.get("id"): p for p in registry["programs"] if isinstance(p, dict)}

    lease_token = secrets.token_hex(16)

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        eligible = []
        for task in queue["tasks"]:
            if task.get("status") != "QUEUED" or task.get("task_id") not in eligible_task_ids:
                continue
            if datetime.fromisoformat(task["not_before"].replace("Z", "+00:00")) > now:
                continue
            policy = authorize(task, by_id)
            eligible.append((task, policy))
        if not eligible:
            validate_candidate(queue, registry)
            return queue, None
        eligible.sort(key=lambda pair: (-pair[0]["priority"], pair[0]["created_at"], pair[0]["task_id"]))
        task, policy = eligible[0]
        task["status"] = "CLAIMED"
        task["attempts"] += 1
        task["state_history"].append("CLAIMED")
        task["lease"] = {
            "owner": worker_id, "token": lease_token,
            "expires_at": stamp(now + timedelta(seconds=policy["timeout_seconds"])),
        }
        queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, task
    return store.mutate(mutate)


def complete_remote(task_id: str, worker_id: str, lease_token: str, *,
                    success: bool, store: GitHubContentsQueueStore,
                    registry: dict, result: dict | None = None,
                    error: dict | None = None, now: datetime | None = None) -> dict:
    now = now or now_utc()
    by_id = {p.get("id"): p for p in registry["programs"] if isinstance(p, dict)}

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        task = next((item for item in queue["tasks"] if item.get("task_id") == task_id), None)
        if task is None:
            raise ValueError(f"unknown task_id: {task_id}")
        lease = task.get("lease")
        if task.get("status") != "CLAIMED" or not isinstance(lease, dict):
            raise ValueError("task is not currently claimed")
        if lease.get("owner") != worker_id or not secrets.compare_digest(str(lease.get("token", "")), str(lease_token)):
            raise ValueError("lease owner or token mismatch")
        if datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00")) <= now:
            raise ValueError("lease has expired; recover the task before completing it")
        authorize(task, by_id)
        if success and not isinstance(result, dict):
            raise ValueError("successful completion requires a result object")
        if not success and not isinstance(error, dict):
            raise ValueError("failed completion requires an error object")
        task["lease"] = None
        if success:
            task["status"] = "VERIFYING"
            task["result"] = result
            task["last_error"] = None
            task["verification"] = None
            task["state_history"].append("VERIFYING")
        else:
            task["last_error"] = error
            task["state_history"].append("FAILED")
            if task["attempts"] < task["max_attempts"]:
                task["status"] = "QUEUED"
                task["state_history"].append("QUEUED")
                task["not_before"] = stamp(now + timedelta(seconds=min(900, 30 * (2 ** max(0, task["attempts"] - 1)))))
            else:
                task["status"] = "DEAD_LETTER"
                task["state_history"].append("DEAD_LETTER")
        queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, task
    return store.mutate(mutate)


def recover_remote(store: GitHubContentsQueueStore, registry: dict, now: datetime | None = None) -> list[dict]:
    now = now or now_utc()

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        recovered = []
        for task in queue["tasks"]:
            if task.get("status") != "CLAIMED":
                continue
            lease = task.get("lease") or {}
            if datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00")) > now:
                continue
            task["lease"] = None
            task["last_error"] = {"type": "lease_expired", "message": "Worker lease expired before completion."}
            if task["attempts"] < task["max_attempts"]:
                task["status"] = "QUEUED"
                task["state_history"].append("QUEUED")
                task["not_before"] = stamp(now + timedelta(seconds=min(900, 30 * (2 ** max(0, task["attempts"] - 1)))))
            else:
                task["status"] = "DEAD_LETTER"
                task["state_history"].append("DEAD_LETTER")
            recovered.append(task)
        if recovered:
            queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, recovered
    return store.mutate(mutate)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--queue-path", default="automation/task_queue.json")
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    subs = parser.add_subparsers(dest="command", required=True)
    enqueue = subs.add_parser("enqueue")
    enqueue.add_argument("--task-json", type=Path, required=True)
    complete = subs.add_parser("complete")
    complete.add_argument("--task-id", required=True)
    complete.add_argument("--worker-id", required=True)
    complete.add_argument("--lease-token", required=True)
    complete.add_argument("--result-json", type=Path)
    complete.add_argument("--error-json", type=Path)
    recover = subs.add_parser("recover-expired")
    subs.add_parser("validate")
    args = parser.parse_args()
    try:
        store = make_store(args.repository, args.branch, args.queue_path)
        registry = load_registry(args.registry)
        if args.command == "enqueue":
            payload = json.loads(args.task_json.read_text(encoding="utf-8"))
            output = enqueue_remote(payload, store, registry)
        elif args.command == "complete":
            if bool(args.result_json) == bool(args.error_json):
                raise ValueError("provide exactly one of --result-json or --error-json")
            if args.result_json:
                result = json.loads(args.result_json.read_text(encoding="utf-8"))
                output = complete_remote(args.task_id, args.worker_id, args.lease_token,
                                          success=True, result=result, store=store, registry=registry)
            else:
                error = json.loads(args.error_json.read_text(encoding="utf-8"))
                output = complete_remote(args.task_id, args.worker_id, args.lease_token,
                                          success=False, error=error, store=store, registry=registry)
        elif args.command == "recover-expired":
            recovered = recover_remote(store, registry)
            output = {"recovered_count": len(recovered), "tasks": recovered}
        else:
            snapshot = store.read()
            validate_envelope(snapshot.document)
            validate_candidate(snapshot.document, registry)
            output = {"valid": True, "revision": snapshot.document["revision"],
                      "task_count": len(snapshot.document["tasks"]), "blob_sha": snapshot.content_sha}
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (ValueError, OSError, json.JSONDecodeError, QueueStoreError) as exc:
        print(f"REMOTE TASK QUEUE ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
