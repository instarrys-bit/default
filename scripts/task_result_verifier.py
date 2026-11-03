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
    if kind is not None and kind not in VALID_TYPES:
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
        if key in schema and (isinstance(schema[key], bool) or not isinstance(schema[key], (int, float))):
            raise ValueError(f"{path}.{key} must be numeric")


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
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
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
            if not math.isfinite(current):
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
                          now: datetime | None = None) -> dict:
    now = now or now_utc()
    adapter_items = adapters.get("adapters")
    if not isinstance(adapter_items, list):
        raise ValueError("execution adapter inventory is invalid")
    by_target = {
        item.get("target_program_id"): item
        for item in adapter_items if isinstance(item, dict)
    }
    verified: list[str] = []
    rejected: list[str] = []
    blocked: list[dict] = []

    def mutate(queue: dict):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        changed = False
        for task in queue["tasks"]:
            if task.get("status") != "VERIFYING":
                continue
            target = task.get("target_program_id")
            adapter = by_target.get(target)
            if (not isinstance(adapter, dict) or adapter.get("enabled") is not True
                    or adapter.get("interface_status") != "reviewed"
                    or not isinstance(adapter.get("output_contract"), dict)):
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
                verified.append(task["task_id"])
            changed = True
        if changed:
            queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, {"verified": verified, "rejected": rejected, "blocked": blocked}

    result = store.mutate(mutate)
    return result


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
    except (ValueError, OSError) as exc:
        print(f"RESULT VERIFICATION ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
