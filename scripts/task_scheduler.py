#!/usr/bin/env python3
"""Deny-by-default one-shot scheduler for reviewed Python execution adapters."""
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
    claim_remote, complete_remote, make_store, recover_remote, validate_candidate, validate_envelope,
)
from task_queue_runtime import authorize, now_utc
from github_queue_store import QueueStoreError
from task_result_verifier import (
    validate_json_schema, validate_schema_definition, verify_pending_remote,
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
            if adapter.get("interface_status") != "reviewed":
                raise ValueError("target adapter interface is not reviewed")
            if adapter.get("adapter_type") != "python_cli":
                raise ValueError("this scheduler version only executes reviewed python_cli adapters")
            if task["requester_program_id"] not in adapter.get("allowed_callers", []):
                raise ValueError("requester is not in the adapter caller allowlist")
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
            timeout = adapter.get("timeout_seconds")
            policy_timeout = target.get("orchestration", {}).get("timeout_seconds")
            if (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1 or timeout > 300
                    or isinstance(policy_timeout, bool) or not isinstance(policy_timeout, int)
                    or timeout >= policy_timeout):
                raise ValueError("adapter timeout must be 1-300 seconds and shorter than the registered task lease")
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
            success=False, error=error, store=store, registry=registry, now=now_utc(),
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


def execute_claimed_task(task: dict, adapter: dict, store, registry: dict,
                         adapters: dict, root: Path = ROOT,
                         now: datetime | None = None) -> dict:
    now = now or now_utc()
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
        try:
            with without_parent_secrets():
                completed = subprocess.run(
                    command,
                    cwd=root,
                    env=safe_child_environment(root),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=adapter["timeout_seconds"],
                    check=False,
                )
        except subprocess.TimeoutExpired:
            ensure_protected_config_unchanged(protected_digest, task, store, registry, root)
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
        task = claim_remote(
            worker_id, store, registry, eligible_task_ids=eligible, now=iteration_now
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
    parser.add_argument("command", choices=["plan", "run-once"])
    args = parser.parse_args()
    try:
        store = make_store(args.repository, args.branch, args.queue_path)
        registry = load_object(args.registry, "program registry")
        adapters = load_object(args.adapters, "execution adapter inventory")
        if args.command == "plan":
            plan = build_execution_plan(store.read().document, registry, adapters)
            print(json.dumps(plan, ensure_ascii=False))
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
