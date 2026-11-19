#!/usr/bin/env python3
"""GitHub-backed task queue runtime using SHA-CAS for every state mutation."""
from __future__ import annotations


import argparse
import json
import os
import re
import secrets
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from github_queue_store import GitHubContentsQueueStore, QueueStoreError
from task_queue_runtime import (
    authorize, manual_authorization_context_from_environment, validate_manual_authorization,
    manual_authorization_record, validate_manual_authorization_consumption, now_utc, stamp,
)
from task_queue import validate_task_queue
from resource_lease_runtime import (
    acquire_resource_leases_in_queue, extend_resource_leases_for_verification,
    release_resource_leases_in_queue,
)


AUTO_PRODUCTION_DECISIONS = {"INPUT_CHANGED", "SCHEDULE_DUE", "RECOVERY_REQUIRED"}

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
               path: str = "automation/task_queue.json",
               token: str | None = None) -> GitHubContentsQueueStore:
    repository = repository or os.environ.get("GITHUB_REPOSITORY", "")
    branch = branch or os.environ.get("GITHUB_REF_NAME", "main")
    if not repository:
        raise ValueError("repository is required (or set GITHUB_REPOSITORY)")
    return GitHubContentsQueueStore(repository, path, branch=branch, token=token)


def enqueue_remote(task: dict, store: GitHubContentsQueueStore,
                   registry: dict, now: datetime | None = None,
                   precondition=None) -> dict:
    if not isinstance(task, dict):
        raise ValueError("task payload must be an object")
    now = now or now_utc()
    programs = registry["programs"]
    by_id = {p.get("id"): p for p in programs if isinstance(p, dict)}
    authorization = validate_manual_authorization(task, manual_authorization_context_from_environment())
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
                if authorization:
                    validate_manual_authorization_consumption(queue, old, authorization)
                validate_candidate(queue, registry)
                return queue, {"created": False, "task": old}
        if precondition is not None:
            if not callable(precondition):
                raise ValueError("enqueue precondition must be callable")
            precondition(queue)
        incoming_decision = payload.get("production_decision")
        incoming_fingerprint = payload.get("production_fingerprint")
        if (task.get("target_program_id") == "workflow_auto_sync"
                and incoming_decision in AUTO_PRODUCTION_DECISIONS
                and isinstance(incoming_fingerprint, str)
                and re.fullmatch(r"[0-9a-f]{64}", incoming_fingerprint)):
            for old in queue["tasks"]:
                old_input = old.get("input") if isinstance(old.get("input"), dict) else {}
                old_decision = old_input.get("production_decision")
                old_fingerprint = old_input.get("production_fingerprint")
                if (old.get("target_program_id") == "workflow_auto_sync"
                        and old.get("status") == "QUEUED"
                        and old.get("lease") is None
                        and old.get("dispatch_intent") is None
                        and old_decision in AUTO_PRODUCTION_DECISIONS
                        and old_fingerprint != incoming_fingerprint):
                    old["status"] = "CANCELLED"
                    old["state_history"].append("CANCELLED")
                    old["last_error"] = {
                        "type": "stale_production_input_superseded",
                        "message": "Queued production task was superseded before claim because current main has a different production input fingerprint.",
                        "superseded_by_fingerprint": incoming_fingerprint,
                        "superseded_by_idempotency_key": idem,
                    }
        if authorization:
            ledger = queue.setdefault("manual_authorizations", {})
            if not isinstance(ledger, dict):
                raise ValueError("manual authorization consumption ledger must be an object")
            if authorization["run_id"] in ledger:
                raise ValueError("manual authorization has already been consumed by another task")
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
        if authorization:
            queue["manual_authorizations"][authorization["run_id"]] = manual_authorization_record(
                item, authorization, stamp(now)
            )
        queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, {"created": True, "task": item}
    return store.mutate(mutate)


def claim_remote(worker_id: str, store: GitHubContentsQueueStore,
                 registry: dict, *, eligible_task_ids: set[str],
                 resource_keys_by_target: dict | None = None,
                 now: datetime | None = None) -> dict | None:
    if not isinstance(worker_id, str) or not worker_id.strip():
        raise ValueError("worker_id is required")
    if not isinstance(eligible_task_ids, set) or any(not isinstance(item, str) for item in eligible_task_ids):
        raise ValueError("eligible_task_ids must be a set of task IDs supplied by the reviewed scheduler")
    now = now or now_utc()
    by_id = {p.get("id"): p for p in registry["programs"] if isinstance(p, dict)}

    resource_keys_by_target = resource_keys_by_target or {}
    if not isinstance(resource_keys_by_target, dict):
        raise ValueError("resource_keys_by_target must be an object")
    lease_tokens = {task_id: secrets.token_hex(16) for task_id in eligible_task_ids}
    resource_lease_ids = {task_id: secrets.token_hex(16) for task_id in eligible_task_ids}

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        eligible = []
        for task in queue["tasks"]:
            if task.get("status") != "QUEUED" or task.get("task_id") not in eligible_task_ids:
                continue
            if datetime.fromisoformat(task["not_before"].replace("Z", "+00:00")) > now:
                continue
            authorization = validate_manual_authorization(task, manual_authorization_context_from_environment())
            validate_manual_authorization_consumption(queue, task, authorization)
            policy = authorize(task, by_id)
            eligible.append((task, policy))
        if not eligible:
            validate_candidate(queue, registry)
            return queue, None
        eligible.sort(key=lambda pair: (
            0 if (
                pair[0].get("target_program_id") == "script_assess_sources"
                and isinstance(pair[0].get("idempotency_key"), str)
                and ":artifact-recovery:" in pair[0]["idempotency_key"]
            ) else 1,
            -pair[0]["priority"], pair[0]["created_at"], pair[0]["task_id"],
        ))
        for task, policy in eligible:
            task["status"] = "CLAIMED"
            task["attempts"] += 1
            task["state_history"].append("CLAIMED")
            task["lease"] = {
                "owner": worker_id, "token": lease_tokens[task["task_id"]],
                "expires_at": stamp(now + timedelta(seconds=policy["timeout_seconds"])),
            }
            resource_spec = resource_keys_by_target.get(task["target_program_id"])
            if resource_spec is not None:
                if not isinstance(resource_spec, dict):
                    raise ValueError("resource contract must be an object")
                acquired = acquire_resource_leases_in_queue(
                    queue, task, worker_id, task["lease"]["token"],
                    resource_spec.get("resource_keys"),
                    lease_seconds=resource_spec.get("lease_seconds", 300),
                    now=now, lease_id=resource_lease_ids[task["task_id"]],
                )
                if not acquired.get("acquired"):
                    task["status"] = "QUEUED"
                    task["attempts"] -= 1
                    task["state_history"].pop()
                    task["lease"] = None
                    continue
                task["resource_lease"] = {
                    "status": "ACTIVE",
                    "resources": acquired["resources"],
                    "lease_seconds": acquired["lease_seconds"],
                    "acquired_at": stamp(now),
                    "expires_at": acquired["expires_at"],
                }
            queue["revision"] += 1
            validate_candidate(queue, registry)
            return queue, task
        validate_candidate(queue, registry)
        return queue, None
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
        authorization = validate_manual_authorization(task, manual_authorization_context_from_environment())
        validate_manual_authorization_consumption(queue, task, authorization)
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
            extend_resource_leases_for_verification(queue, task, now)
        else:
            release_resource_leases_in_queue(queue, task, now)
            evidence = error.get("evidence") if isinstance(error, dict) else None
            workflow_cancelled = (
                isinstance(evidence, dict) and evidence.get("conclusion") == "cancelled"
            )
            task["last_error"] = error
            if workflow_cancelled:
                # A cancelled Actions run is not a deterministic production failure.
                # Preserve its evidence, release the resource fence, and record the
                # correct terminal lifecycle state instead of exhausting retries into
                # DEAD_LETTER and inflating the dashboard's failure count.
                task["status"] = "CANCELLED"
                task["state_history"].append("CANCELLED")
            else:
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
            try:
                release_resource_leases_in_queue(queue, task, now)
            except ValueError:
                # A newer fencing epoch already owns the resource; never release it.
                pass
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



def resolve_superseded_dead_letters(
    store: GitHubContentsQueueStore,
    registry: dict,
    current_main_sha: str,
    now: datetime | None = None,
) -> list[dict]:
    """Resolve terminal tasks whose source inputs are provably obsolete."""
    now = now or now_utc()
    if not isinstance(current_main_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", current_main_sha):
        raise ValueError("current main SHA must be a full lowercase Git commit SHA")

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        resolved = []
        replacements = [
            task for task in queue["tasks"]
            if task.get("target_program_id") == "workflow_auto_sync"
            and task.get("status") in {"QUEUED", "CLAIMED", "VERIFYING"}
        ]
        replacement_ids = {
            task.get("task_id")
            for task in replacements
            if (task.get("input") or {}).get("baseline_source_sha") == current_main_sha
            or (task.get("dispatch_intent") or {}).get("requested_head_sha") == current_main_sha
        }
        replacement_task_id = sorted(replacement_ids)[0] if replacement_ids else None

        for task in queue["tasks"]:
            if task.get("status") != "DEAD_LETTER":
                continue
            if task.get("lease") is not None:
                raise ValueError("DEAD_LETTER task unexpectedly retains a worker lease")
            resource_lease = task.get("resource_lease")
            if isinstance(resource_lease, dict) and resource_lease.get("status") == "ACTIVE":
                raise ValueError("DEAD_LETTER task unexpectedly retains an active resource lease")

            target = task.get("target_program_id")
            payload = task.get("input") if isinstance(task.get("input"), dict) else {}
            last_error = task.get("last_error") if isinstance(task.get("last_error"), dict) else {}
            reason = None
            source_sha = None
            evidence = {}

            if target == "workflow_auto_sync":
                intent = task.get("dispatch_intent") if isinstance(task.get("dispatch_intent"), dict) else {}
                failure_evidence = last_error.get("evidence") if isinstance(last_error.get("evidence"), dict) else {}
                source_sha = payload.get("baseline_source_sha") or intent.get("requested_head_sha")
                conclusion = failure_evidence.get("conclusion")
                if failure_evidence.get("status") != "completed" or conclusion not in {"failure", "cancelled", "timed_out"}:
                    continue
                if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
                    continue
                if source_sha == current_main_sha:
                    continue
                reason = "completed production workflow belongs to an older main input; current Watchdog reconciliation owns the replacement decision"
                evidence = {
                    "original_source_sha": source_sha,
                    "workflow_run_id": failure_evidence.get("run_id"),
                    "workflow_conclusion": conclusion,
                    "requested_head_sha": intent.get("requested_head_sha"),
                }
            elif target == "script_assess_sources":
                predecessor = payload.get("predecessor")
                valid_predecessor = (
                    isinstance(predecessor, dict)
                    and isinstance(predecessor.get("workflow_run_id"), str)
                    and predecessor["workflow_run_id"].isdigit()
                    and isinstance(predecessor.get("artifact_sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", predecessor["artifact_sha256"])
                )
                if valid_predecessor or last_error.get("type") != "artifact_publication_failed":
                    continue
                reason = "legacy assessment canary has no trusted discovery predecessor and cannot be safely replayed"
                evidence = {"legacy_task_id": task.get("task_id")}
            else:
                continue

            task["status"] = "CANCELLED"
            task["state_history"].append("CANCELLED")
            task["resolution"] = {
                "schema_version": 1,
                "disposition": "superseded",
                "reason": reason,
                "superseded_by_main_sha": current_main_sha,
                "replacement_task_id": replacement_task_id if target == "workflow_auto_sync" else None,
                "evidence": evidence,
                "resolved_at": stamp(now),
            }
            resolved.append(task)

        if resolved:
            queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, resolved

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
    snapshot = subs.add_parser("snapshot")
    snapshot.add_argument("--output", type=Path, required=True)
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
        elif args.command == "snapshot":
            snapshot = store.read()
            validate_envelope(snapshot.document)
            validate_candidate(snapshot.document, registry)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(snapshot.document, ensure_ascii=False) + "\n", encoding="utf-8")
            output = {"valid": True, "revision": snapshot.document["revision"],
                      "task_count": len(snapshot.document["tasks"]), "snapshot_path": str(args.output)}
        else:
            snapshot = store.read()
            validate_envelope(snapshot.document)
            validate_candidate(snapshot.document, registry)
            output = {"valid": True, "revision": snapshot.document["revision"],
                      "task_count": len(snapshot.document["tasks"]), "content_sha": snapshot.content_sha}
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except (ValueError, OSError, json.JSONDecodeError, QueueStoreError) as exc:
        print(f"REMOTE TASK QUEUE ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
