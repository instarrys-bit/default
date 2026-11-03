#!/usr/bin/env python3
"""Fail-closed inventory and dependency validation for automation programs."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("automation/program_registry.json")
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,79}$")


def discover_program_paths(root: Path) -> set[str]:
    scripts = {
        path.relative_to(root).as_posix()
        for path in (root / "scripts").rglob("*.py")
        if path.is_file()
    }
    workflows = {
        path.relative_to(root).as_posix()
        for path in (root / ".github" / "workflows").iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    } if (root / ".github" / "workflows").is_dir() else set()
    return scripts | workflows


def validate_registry(root: Path = ROOT, registry_path: Path | None = None) -> dict:
    registry_path = registry_path or (root / REGISTRY_PATH)
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read program registry: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("program registry schema_version must be 1")
    policy = payload.get("registry_policy")
    if not isinstance(policy, dict):
        raise ValueError("registry_policy must be an object")
    for field in ("purpose", "registration_required_for", "collaboration_rule", "permission_rule", "activation_rule"):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            raise ValueError(f"registry_policy.{field} is required")

    programs = payload.get("programs")
    if not isinstance(programs, list) or not programs:
        raise ValueError("programs must be a non-empty array")

    by_id = {}
    by_path = {}
    required_fields = (
        "id", "path", "kind", "responsibility", "capabilities", "invocation",
        "inputs", "outputs", "depends_on", "dispatches", "permission_boundary", "health_check", "orchestration",
    )
    for item in programs:
        if not isinstance(item, dict):
            raise ValueError("each program entry must be an object")
        missing = [field for field in required_fields if field not in item]
        if missing:
            raise ValueError("program entry is missing fields: " + ", ".join(missing))
        program_id = item["id"]
        path = item["path"]
        if not isinstance(program_id, str) or not ID_RE.fullmatch(program_id):
            raise ValueError(f"invalid program id: {program_id!r}")
        if program_id in by_id:
            raise ValueError(f"duplicate program id: {program_id}")
        if not isinstance(path, str) or path in by_path:
            raise ValueError(f"missing or duplicate program path: {path!r}")
        if path.startswith("/") or ".." in Path(path).parts:
            raise ValueError(f"program path must stay inside the repository: {path}")
        if item["kind"] not in {"python_component", "github_actions_workflow"}:
            raise ValueError(f"unsupported program kind for {program_id}")
        if item["kind"] == "python_component" and not path.startswith("scripts/"):
            raise ValueError(f"Python component must live under scripts/: {program_id}")
        if item["kind"] == "github_actions_workflow" and not path.startswith(".github/workflows/"):
            raise ValueError(f"workflow must live under .github/workflows/: {program_id}")
        for field in ("responsibility", "invocation", "permission_boundary", "health_check"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError(f"{program_id}.{field} must be a non-empty string")
        for field in ("capabilities", "inputs", "outputs", "depends_on", "dispatches"):
            value = item[field]
            if not isinstance(value, list) or any(not isinstance(entry, str) or not entry.strip() for entry in value):
                raise ValueError(f"{program_id}.{field} must be an array of non-empty strings")
            if len(value) != len(set(value)):
                raise ValueError(f"{program_id}.{field} contains duplicates")
        if not item["capabilities"]:
            raise ValueError(f"{program_id} must declare at least one capability")
        orchestration = item["orchestration"]
        if not isinstance(orchestration, dict):
            raise ValueError(f"{program_id}.orchestration must be an object")
        if not isinstance(orchestration.get("enabled"), bool):
            raise ValueError(f"{program_id}.orchestration.enabled must be boolean")
        callers = orchestration.get("allowed_callers")
        if not isinstance(callers, list) or any(not isinstance(caller, str) or not caller for caller in callers):
            raise ValueError(f"{program_id}.orchestration.allowed_callers must be an array of program IDs")
        if len(callers) != len(set(callers)):
            raise ValueError(f"{program_id}.orchestration.allowed_callers contains duplicates")
        max_attempts = orchestration.get("max_attempts")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 0 <= max_attempts <= 5:
            raise ValueError(f"{program_id}.orchestration.max_attempts must be an integer from 0 to 5")
        timeout = orchestration.get("timeout_seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
            raise ValueError(f"{program_id}.orchestration.timeout_seconds must be an integer from 1 to 3600")
        if not orchestration["enabled"] and callers:
            raise ValueError(f"{program_id} cannot allow callers while orchestration is disabled")
        by_id[program_id] = item
        by_path[path] = item

    expected_paths = discover_program_paths(root)
    registered_paths = set(by_path)
    missing_paths = sorted(expected_paths - registered_paths)
    stale_paths = sorted(registered_paths - expected_paths)
    if missing_paths or stale_paths:
        details = []
        if missing_paths:
            details.append("unregistered program files: " + ", ".join(missing_paths))
        if stale_paths:
            details.append("registry paths not present in repository: " + ", ".join(stale_paths))
        raise ValueError("; ".join(details))

    for program_id, item in by_id.items():
        orchestration = item["orchestration"]
        unknown_callers = sorted(set(orchestration["allowed_callers"]) - set(by_id))
        if unknown_callers:
            raise ValueError(f"{program_id}.orchestration references unknown callers: {', '.join(unknown_callers)}")
        if orchestration["enabled"] and not orchestration["allowed_callers"]:
            raise ValueError(f"{program_id} orchestration cannot be enabled without explicit allowed callers")
        for field in ("depends_on", "dispatches"):
            unknown = sorted(set(item[field]) - set(by_id))
            if unknown:
                raise ValueError(f"{program_id}.{field} references unknown programs: {', '.join(unknown)}")
        if program_id in item["depends_on"] or program_id in item["dispatches"]:
            raise ValueError(f"{program_id} cannot depend on or dispatch itself")
        if item["kind"] == "python_component" and item["dispatches"]:
            raise ValueError(f"Python component {program_id} cannot declare workflow dispatch targets")

    # Workflow-to-script and workflow-to-workflow edges must match the actual
    # commands in the workflow file; editing a caller requires registry review.
    for path, item in by_path.items():
        if item["kind"] != "github_actions_workflow":
            continue
        content = (root / path).read_text(encoding="utf-8")
        actual_scripts = {
            "script_" + match.group(1)[:-3]
            for match in re.finditer(r"scripts/([A-Za-z0-9_.-]+\.py)", content)
        }
        actual_dispatches = {
            "workflow_" + re.sub(r"\.(yml|yaml)$", "", match.group(1)).replace("-", "_")
            for match in re.finditer(r"gh workflow run ([A-Za-z0-9_.-]+)", content)
        }
        if actual_scripts != set(item["depends_on"]):
            missing = sorted(actual_scripts - set(item["depends_on"]))
            extra = sorted(set(item["depends_on"]) - actual_scripts)
            raise ValueError(
                f"{item['id']} script dependency mismatch; missing={missing}, extra={extra}"
            )
        if actual_dispatches != set(item["dispatches"]):
            missing = sorted(actual_dispatches - set(item["dispatches"]))
            extra = sorted(set(item["dispatches"]) - actual_dispatches)
            raise ValueError(
                f"{item['id']} workflow dispatch mismatch; missing={missing}, extra={extra}"
            )

    return {
        "valid": True,
        "program_count": len(programs),
        "python_component_count": sum(p["kind"] == "python_component" for p in programs),
        "workflow_count": sum(p["kind"] == "github_actions_workflow" for p in programs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()
    try:
        result = validate_registry(args.root, args.registry)
    except ValueError as exc:
        print(f"PROGRAM REGISTRY INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
