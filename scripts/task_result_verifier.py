#!/usr/bin/env python3
"""Deterministically verify remote task results against reviewed adapter contracts."""
from __future__ import annotations


import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

from remote_task_queue_runtime import (
    make_store, validate_candidate, validate_envelope,
)
from task_queue_runtime import now_utc, stamp
from github_queue_store import QueueStoreError
from github_workflow_adapter import GitHubWorkflowClient, WorkflowAPIError, inspect_correlated_run
from resource_lease_runtime import renew_resource_leases_in_queue, release_resource_leases_in_queue


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "automation" / "program_registry.json"
ADAPTERS = ROOT / "automation" / "execution_adapters.json"
VERIFIER_ID = "script_task_result_verifier"
ALLOWED_SCHEMA_KEYS = {
    "$schema", "title", "description", "type", "properties", "required",
    "additionalProperties", "items", "enum", "const", "minLength",
    "maxLength", "minimum", "maximum", "minItems", "maxItems",
}
VALID_TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


def load_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _check_schema_definition(schema: object, path: str = "$schema", depth: int = 0) -> None:
    if depth > 32:
        raise ValueError(f"{path} exceeds maximum schema nesting depth")
    if not isinstance(schema, dict):
        raise ValueError(f"{path} must be an object")
    unknown = sorted(set(schema) - ALLOWED_SCHEMA_KEYS)
    if unknown:
        raise ValueError(f"{path} uses unsupported schema keywords: {', '.join(unknown)}")
    kind = schema.get("type")
    if kind is not None and (not isinstance(kind, str) or kind not in VALID_TYPES):
        raise ValueError(f"{path}.type is unsupported")
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict) or any(not isinstance(k, str) for k in properties):
            raise ValueError(f"{path}.properties must be an object")
        for key, child in properties.items():
            _check_schema_definition(child, f"{path}.properties.{key}", depth + 1)
    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or any(not isinstance(x, str) for x in required):
            raise ValueError(f"{path}.required must be an array of strings")
        if len(required) != len(set(required)):
            raise ValueError(f"{path}.required contains duplicates")
    if "additionalProperties" in schema:
        extra = schema["additionalProperties"]
        if not isinstance(extra, bool):
            _check_schema_definition(extra, f"{path}.additionalProperties", depth + 1)
    if "items" in schema:
        _check_schema_definition(schema["items"], f"{path}.items", depth + 1)
    if "enum" in schema and not isinstance(schema["enum"], list):
        raise ValueError(f"{path}.enum must be an array")
    for key in ("minLength", "maxLength", "minItems", "maxItems"):
        if key in schema and (isinstance(schema[key], bool) or not isinstance(schema[key], int) or schema[key] < 0):
            raise ValueError(f"{path}.{key} must be a non-negative integer")
    for key in ("minimum", "maximum"):
        if key in schema and (
            isinstance(schema[key], bool) or not isinstance(schema[key], (int, float))
            or (isinstance(schema[key], float) and not math.isfinite(schema[key]))
        ):
            raise ValueError(f"{path}.{key} must be a finite number")
    if "minLength" in schema and "maxLength" in schema and schema["minLength"] > schema["maxLength"]:
        raise ValueError(f"{path} minLength exceeds maxLength")
    if "minItems" in schema and "maxItems" in schema and schema["minItems"] > schema["maxItems"]:
        raise ValueError(f"{path} minItems exceeds maxItems")


def validate_schema_definition(schema: object) -> None:
    """Validate the supported schema subset without evaluating a result value."""
    _check_schema_definition(schema)


def _matches_type(value: object, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and math.isfinite(value)
        )
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    return False


def validate_json_schema(value: object, schema: dict) -> list[str]:
    """Validate a deliberately small JSON Schema subset; unsupported keywords fail closed."""
    _check_schema_definition(schema)
    errors: list[str] = []

    def visit(current: object, rule: dict, path: str, depth: int = 0) -> None:
        if depth > 32:
            errors.append(f"{path}: maximum validation depth exceeded")
            return
        kind = rule.get("type")
        if kind is not None and not _matches_type(current, kind):
            errors.append(f"{path}: expected {kind}")
            return
        if "const" in rule and current != rule["const"]:
            errors.append(f"{path}: value does not match const")
        if "enum" in rule and current not in rule["enum"]:
            errors.append(f"{path}: value is not in enum")
        if isinstance(current, str):
            if "minLength" in rule and len(current) < rule["minLength"]:
                errors.append(f"{path}: string is shorter than minLength")
            if "maxLength" in rule and len(current) > rule["maxLength"]:
                errors.append(f"{path}: string is longer than maxLength")
        if isinstance(current, (int, float)) and not isinstance(current, bool):
            if isinstance(current, float) and not math.isfinite(current):
                errors.append(f"{path}: number must be finite")
            if "minimum" in rule and current < rule["minimum"]:
                errors.append(f"{path}: number is below minimum")
            if "maximum" in rule and current > rule["maximum"]:
                errors.append(f"{path}: number is above maximum")
        if isinstance(current, list):
            if "minItems" in rule and len(current) < rule["minItems"]:
                errors.append(f"{path}: array has fewer than minItems")
            if "maxItems" in rule and len(current) > rule["maxItems"]:
                errors.append(f"{path}: array has more than maxItems")
            if "items" in rule:
                for index, item in enumerate(current):
                    visit(item, rule["items"], f"{path}[{index}]", depth + 1)
        if isinstance(current, dict):
            properties = rule.get("properties", {})
            for key in rule.get("required", []):
                if key not in current:
                    errors.append(f"{path}: missing required property {key}")
            for key, item in current.items():
                if key in properties:
                    visit(item, properties[key], f"{path}.{key}", depth + 1)
                elif rule.get("additionalProperties") is False:
                    errors.append(f"{path}: unexpected property {key}")
                elif isinstance(rule.get("additionalProperties"), dict):
                    visit(item, rule["additionalProperties"], f"{path}.{key}", depth + 1)

    visit(value, schema, "$")
    return errors


def verify_pending_remote(store, registry: dict, adapters: dict,
                          now: datetime | None = None, workflow_client=None) -> dict:
    now = now or now_utc()
    adapter_items = adapters.get("adapters")
    if adapters.get("schema_version") != 1 or not isinstance(adapter_items, list):
        raise ValueError("execution adapter inventory is invalid")
    by_target = {}
    for item in adapter_items:
        if not isinstance(item, dict):
            raise ValueError("execution adapter entries must be objects")
        target_id = item.get("target_program_id")
        if not isinstance(target_id, str) or not target_id:
            raise ValueError("execution adapter target_program_id is required")
        if target_id in by_target:
            raise ValueError(f"duplicate execution adapter for {target_id}")
        by_target[target_id] = item

    # Network reads happen before the CAS mutator. The mutator remains pure and
    # may safely be replayed if another worker advances the queue revision.
    snapshot = store.read().document
    workflow_observations = {}
    workflow_tasks = [
        task for task in snapshot.get("tasks", [])
        if isinstance(task, dict) and (
            task.get("status") == "VERIFYING"
            or (
                task.get("status") in {"CLAIMED", "QUEUED", "DEAD_LETTER"}
                and isinstance(task.get("dispatch_intent"), dict)
                and not isinstance(task.get("verification"), dict)
            )
        )
        and by_target.get(task.get("target_program_id"), {}).get("adapter_type") == "github_actions_workflow"
    ]
    if workflow_tasks:
        if workflow_client is None:
            try:
                workflow_client = GitHubWorkflowClient(store.repository, token=store.token)
            except (AttributeError, ValueError) as exc:
                for task in workflow_tasks:
                    workflow_observations[task["task_id"]] = {
                        "state": "error", "reason": f"workflow API client unavailable: {exc}"
                    }
        if workflow_client is not None:
            for task in workflow_tasks:
                adapter = by_target.get(task.get("target_program_id"), {})
                intent = task.get("dispatch_intent") or task.get("result")
                if (adapter.get("enabled") is not True
                        or adapter.get("interface_status") != "workflow_dispatch_reviewed"
                        or not isinstance(adapter.get("workflow"), dict)
                        or not isinstance(intent, dict)):
                    workflow_observations[task["task_id"]] = {
                        "state": "error", "reason": "workflow adapter or persisted dispatch intent is not reviewable"
                    }
                    continue
                try:
                    prior_result = task.get("result")
                    prior_evidence = prior_result.get("run_evidence", {}) if isinstance(prior_result, dict) else {}
                    known_run_id = prior_evidence.get("run_id") if isinstance(prior_evidence, dict) else None
                    observation = inspect_correlated_run(
                        workflow_client, intent, known_run_id=known_run_id
                    )
                    # A Watchdog runner can be cancelled after claiming a task and
                    # persisting dispatch intent but before it completes the queue
                    # transition to VERIFYING. Reconcile the child correlation first.
                    # If no child run exists and the exact owning Watchdog run is
                    # terminal for at least two minutes, fence off the ambiguous
                    # dispatch instead of holding production resources for hours.
                    if (
                        task.get("status") == "CLAIMED"
                        and observation.get("state") == "pending"
                        and observation.get("run_id") is None
                    ):
                        lease = task.get("lease") if isinstance(task.get("lease"), dict) else {}
                        owner = lease.get("owner")
                        if isinstance(owner, str) and owner.isdigit():
                            owner_run = workflow_client.get_run(int(owner))
                            owner_updated = owner_run.get("updated_at")
                            owner_path = owner_run.get("path")
                            owner_terminal = (
                                owner_run.get("status") == "completed"
                                and owner_run.get("conclusion") in {"cancelled", "failure", "timed_out"}
                                and owner_run.get("head_branch") == "main"
                                and owner_path == ".github/workflows/automation-watchdog.yml"
                                and isinstance(owner_updated, str)
                            )
                            if owner_terminal:
                                completed_at = datetime.fromisoformat(owner_updated.replace("Z", "+00:00"))
                                if (now - completed_at).total_seconds() >= 120:
                                    observation = {
                                        "state": "abandoned",
                                        "reason": "owning Watchdog run is terminal and no correlated child workflow run exists after the reconciliation grace period",
                                        "owner_run_id": int(owner),
                                        "owner_conclusion": owner_run.get("conclusion"),
                                        "owner_updated_at": owner_updated,
                                    }
                    workflow_observations[task["task_id"]] = observation
                except (WorkflowAPIError, ValueError, KeyError) as exc:
                    workflow_observations[task["task_id"]] = {"state": "error", "reason": str(exc)[:1000]}

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        verified: list[str] = []
        rejected: list[str] = []
        blocked: list[dict] = []
        changed = False
        for task in queue["tasks"]:
            status = task.get("status")
            has_recoverable_intent = (
                status in {"CLAIMED", "QUEUED", "DEAD_LETTER"}
                and isinstance(task.get("dispatch_intent"), dict)
                and not isinstance(task.get("verification"), dict)
            )
            if status != "VERIFYING" and not has_recoverable_intent:
                continue
            target = task.get("target_program_id")
            adapter = by_target.get(target)
            if not isinstance(adapter, dict) or adapter.get("enabled") is not True:
                blocked.append({"task_id": task["task_id"], "reason": "target adapter is not enabled"})
                continue

            if adapter.get("adapter_type") == "github_actions_workflow":
                observation = workflow_observations.get(task["task_id"])
                if isinstance(observation, dict) and observation.get("state") == "abandoned":
                    workflow_contract = adapter.get("workflow", {})
                    contract_sha = hashlib.sha256(
                        json.dumps(workflow_contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                    ).hexdigest()
                    task["result"] = {
                        **(task.get("dispatch_intent") or {}),
                        "dispatch_state": "unknown",
                        "dispatch_uncertainty": observation["reason"],
                    }
                    task["verification"] = {
                        "verifier_program_id": VERIFIER_ID,
                        "verified_at": stamp(now),
                        "contract_sha256": contract_sha,
                        "status": "failed",
                    }
                    task["last_error"] = {
                        "type": "abandoned_scheduler_run_dispatch_outcome_unknown",
                        "message": observation["reason"],
                        "evidence": {
                            "owner_run_id": observation.get("owner_run_id"),
                            "owner_conclusion": observation.get("owner_conclusion"),
                            "owner_updated_at": observation.get("owner_updated_at"),
                            "correlation_id": (task.get("dispatch_intent") or {}).get("correlation_id"),
                        },
                    }
                    if task.get("resource_lease", {}).get("status") == "ACTIVE":
                        try:
                            release_resource_leases_in_queue(queue, task, now)
                        except ValueError:
                            task["resource_lease"]["status"] = "LOST"
                            task["resource_lease"]["lost_at"] = stamp(now)
                    task["lease"] = None
                    task["status"] = "DEAD_LETTER"
                    task["state_history"].append("DEAD_LETTER")
                    rejected.append(task["task_id"])
                    changed = True
                    continue
                if (adapter.get("interface_status") != "workflow_dispatch_reviewed"
                        or not isinstance(adapter.get("workflow"), dict)):
                    blocked.append({"task_id": task["task_id"], "reason": "workflow adapter contract is not reviewed"})
                    continue
                observation = workflow_observations.get(task["task_id"])
                if not isinstance(observation, dict) or observation.get("state") == "error":
                    blocked.append({
                        "task_id": task["task_id"],
                        "reason": observation.get("reason", "workflow run inspection unavailable")
                        if isinstance(observation, dict) else "workflow run inspection unavailable",
                    })
                    continue
                if observation.get("state") == "pending":
                    run_id = observation.get("run_id")
                    if has_recoverable_intent and isinstance(run_id, int):
                        task["result"] = {
                            **task["dispatch_intent"],
                            "dispatch_state": "reconciled",
                            "run_evidence": {
                                "run_id": run_id,
                                "html_url": observation.get("html_url"),
                                "status": observation.get("run_status", "in_progress"),
                            },
                        }
                        task["status"] = "VERIFYING"
                        task["state_history"].append("VERIFYING")
                        changed = True
                    elif status == "VERIFYING" and isinstance(run_id, int):
                        evidence = {
                            "run_id": run_id,
                            "html_url": observation.get("html_url"),
                            "status": observation.get("run_status", "in_progress"),
                        }
                        if task.get("result", {}).get("run_evidence") != evidence:
                            task["result"]["run_evidence"] = evidence
                            changed = True
                    if task.get("resource_lease", {}).get("status") == "ACTIVE":
                        if renew_resource_leases_in_queue(queue, task, now):
                            changed = True
                        else:
                            task["resource_lease"]["status"] = "LOST"
                            task["resource_lease"]["lost_at"] = stamp(now)
                            blocked.append({"task_id": task["task_id"], "reason": "resource lease expired or was fenced by a newer owner while workflow is pending"})
                            changed = True
                    blocked.append({"task_id": task["task_id"], "reason": observation.get("reason", "workflow run is still pending")})
                    continue
                if observation.get("state") not in {"success", "failure"}:
                    blocked.append({"task_id": task["task_id"], "reason": "workflow run inspection returned an unsupported state"})
                    continue

                if has_recoverable_intent:
                    task["result"] = {
                        **task["dispatch_intent"],
                        "dispatch_state": "reconciled",
                    }
                    task["status"] = "VERIFYING"
                    task["state_history"].append("VERIFYING")
                task["result"]["run_evidence"] = observation["evidence"]
                workflow_contract = adapter["workflow"]
                contract_sha = hashlib.sha256(
                    json.dumps(workflow_contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                lease_lost = task.get("resource_lease", {}).get("status") == "LOST"
                passed = observation["state"] == "success" and not lease_lost
                task["verification"] = {
                    "verifier_program_id": VERIFIER_ID,
                    "verified_at": stamp(now),
                    "contract_sha256": contract_sha,
                    "status": "passed" if passed else "failed",
                }
                if passed:
                    task["status"] = "SUCCEEDED"
                    task["last_error"] = None
                    task["state_history"].append("SUCCEEDED")
                    verified.append(task["task_id"])
                else:
                    task["last_error"] = {
                        "type": "workflow_run_failed",
                        "message": ("workflow completed after its resource lease was lost" if lease_lost else observation.get("reason", "GitHub Actions workflow did not succeed")),
                        "evidence": observation.get("evidence"),
                    }
                    task["state_history"].append("FAILED")
                    if task["attempts"] < task["max_attempts"]:
                        task["status"] = "QUEUED"
                        task.pop("dispatch_intent", None)
                        task["state_history"].append("QUEUED")
                        task["not_before"] = stamp(now + timedelta(
                            seconds=min(900, 30 * (2 ** max(0, task["attempts"] - 1)))
                        ))
                    else:
                        task["status"] = "DEAD_LETTER"
                        task["state_history"].append("DEAD_LETTER")
                    rejected.append(task["task_id"])
                if task.get("resource_lease", {}).get("status") == "ACTIVE":
                    try:
                        release_resource_leases_in_queue(queue, task, now)
                    except ValueError:
                        task["resource_lease"]["status"] = "LOST"
                        task["resource_lease"]["lost_at"] = stamp(now)
                # A reconciled workflow may have originated from a CLAIMED task
                # whose scheduler runner was cancelled. Terminal/requeued states
                # must not retain that runner's task lease.
                task["lease"] = None
                changed = True
                continue

            if adapter.get("adapter_type") != "python_cli":
                blocked.append({"task_id": task["task_id"], "reason": "unsupported adapter type"})
                continue
            if adapter.get("interface_status") != "reviewed" or not isinstance(adapter.get("output_contract"), dict):
                blocked.append({"task_id": task["task_id"], "reason": "target has no enabled, reviewed output contract"})
                continue
            schema = adapter["output_contract"]
            errors = validate_json_schema(task.get("result"), schema)
            task["verification"] = {
                "verifier_program_id": VERIFIER_ID,
                "verified_at": stamp(now),
                "contract_sha256": hashlib.sha256(
                    json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                ).hexdigest(),
                "status": "passed" if not errors else "failed",
            }
            if errors:
                task["last_error"] = {
                    "type": "result_verification_failed",
                    "message": "Result did not satisfy the registered output contract.",
                    "details": errors[:20],
                }
                task["state_history"].append("FAILED")
                if task["attempts"] < task["max_attempts"]:
                    task["status"] = "QUEUED"
                    task["state_history"].append("QUEUED")
                    task["not_before"] = stamp(now + timedelta(
                        seconds=min(900, 30 * (2 ** max(0, task["attempts"] - 1)))
                    ))
                else:
                    task["status"] = "DEAD_LETTER"
                    task["state_history"].append("DEAD_LETTER")
                rejected.append(task["task_id"])
            else:
                task["status"] = "SUCCEEDED"
                task["last_error"] = None
                task["state_history"].append("SUCCEEDED")
                if target == "script_assess_sources":
                    checkpoint = task.pop("assessment_checkpoint", None)
                    if isinstance(checkpoint, dict):
                        task["assessment_checkpoint_summary"] = {
                            "batch_id": checkpoint.get("batch_id"),
                            "completed_url_count": len(checkpoint.get("completed", {})),
                            "last_successful_url": checkpoint.get("last_successful_url"),
                        }
                verified.append(task["task_id"])
            if task.get("resource_lease", {}).get("status") == "ACTIVE":
                try:
                    release_resource_leases_in_queue(queue, task, now)
                except ValueError:
                    task["resource_lease"]["status"] = "LOST"
                    task["resource_lease"]["lost_at"] = stamp(now)
            changed = True
        if changed:
            queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, {"verified": verified, "rejected": rejected, "blocked": blocked}

    return store.mutate(mutate)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--queue-path", default="automation/task_queue.json")
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--adapters", type=Path, default=ADAPTERS)
    parser.add_argument("command", choices=["verify-pending"])
    args = parser.parse_args()
    try:
        store = make_store(args.repository, args.branch, args.queue_path)
        registry = load_object(args.registry, "program registry")
        adapters = load_object(args.adapters, "execution adapter inventory")
        print(json.dumps(verify_pending_remote(store, registry, adapters), ensure_ascii=False))
        return 0
    except (ValueError, OSError, QueueStoreError) as exc:
        print(f"RESULT VERIFICATION ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
