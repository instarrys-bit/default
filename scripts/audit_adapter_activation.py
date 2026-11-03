#!/usr/bin/env python3
"""Read-only, deterministic activation-readiness audit for registered adapters."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "automation" / "program_registry.json"
ADAPTERS = ROOT / "automation" / "execution_adapters.json"
WATCHDOG_ID = "workflow_automation_watchdog"
WATCHDOG_JOB = "task-queue-supervision"
REQUIRED_CALLER_SCOPES = {"actions": "write", "contents": "write"}


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def parse_permission_block(lines: list[str], start: int) -> dict[str, str]:
    indent = len(lines[start]) - len(lines[start].lstrip(" "))
    result = {}
    for line in lines[start + 1:]:
        if not line.strip():
            continue
        current_indent = len(line) - len(line.lstrip(" "))
        if current_indent <= indent:
            break
        match = re.fullmatch(r"\s+([a-z-]+):\s*(read|write|none)\s*", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def workflow_permission_sections(content: str) -> list[dict[str, str]]:
    lines = content.splitlines()
    sections = []
    for index, line in enumerate(lines):
        if re.fullmatch(r"\s*permissions:\s*", line):
            sections.append(parse_permission_block(lines, index))
    return sections


def top_level_permissions(content: str) -> dict[str, str]:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if re.fullmatch(r"permissions:\s*", line):
            return parse_permission_block(lines, index)
    return {}


def job_permissions(content: str, job_id: str) -> dict[str, str]:
    lines = content.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if re.fullmatch(rf"  {re.escape(job_id)}:\s*", line)), None)
    if start is None:
        return {}
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*$", lines[i])), len(lines))
    block = lines[start:end]
    permission_index = next((i for i, line in enumerate(block)
                             if re.fullmatch(r"    permissions:\s*", line)), None)
    if permission_index is None:
        return top_level_permissions(content)
    return parse_permission_block(block, permission_index)


def audit_activation_readiness(root: Path = ROOT,
                               registry_path: Path | None = None,
                               adapters_path: Path | None = None) -> dict:
    registry = load_json(registry_path or (root / REGISTRY.relative_to(ROOT)), "program registry")
    inventory = load_json(adapters_path or (root / ADAPTERS.relative_to(ROOT)), "execution adapters")
    programs = registry.get("programs")
    adapters = inventory.get("adapters")
    if not isinstance(programs, list) or not isinstance(adapters, list):
        raise ValueError("program registry and adapter inventory must contain arrays")
    by_program = {p.get("id"): p for p in programs if isinstance(p, dict)}
    by_adapter = {a.get("target_program_id"): a for a in adapters if isinstance(a, dict)}
    if set(by_program) != set(by_adapter):
        raise ValueError("program and adapter inventories do not match")

    watchdog = by_program.get(WATCHDOG_ID)
    watchdog_permissions = {}
    if isinstance(watchdog, dict):
        watchdog_path = root / watchdog["path"]
        if watchdog_path.is_file():
            watchdog_permissions = job_permissions(
                watchdog_path.read_text(encoding="utf-8"), WATCHDOG_JOB
            )
    caller_permissions_ready = all(
        watchdog_permissions.get(scope) == access
        for scope, access in REQUIRED_CALLER_SCOPES.items()
    )

    rows = []
    for program_id in sorted(by_program):
        program = by_program[program_id]
        adapter = by_adapter[program_id]
        orchestration = program.get("orchestration", {})
        reasons = []
        enabled = adapter.get("enabled") is True
        if not enabled:
            reasons.append("adapter is disabled")
        if orchestration.get("enabled") is not True:
            reasons.append("target orchestration is disabled")
        callers = adapter.get("allowed_callers", [])
        if not callers:
            reasons.append("caller allowlist is empty")
        if callers != orchestration.get("allowed_callers", []):
            reasons.append("adapter and registry caller allowlists differ")

        row = {
            "program_id": program_id,
            "kind": program.get("kind"),
            "adapter_type": adapter.get("adapter_type"),
            "enabled": enabled,
            "interface_status": adapter.get("interface_status"),
            "allowed_callers": callers,
            "preactivation_ready": False,
            "least_privilege_canary_candidate": False,
            "write_scopes": [],
            "side_effects": [],
            "blockers": reasons,
        }

        if program.get("kind") == "github_actions_workflow":
            workflow = adapter.get("workflow", {})
            path = root / program["path"]
            if not path.is_file():
                reasons.append("workflow file is missing")
                content = ""
            else:
                content = path.read_text(encoding="utf-8")
            if workflow.get("dispatchable") is not True:
                reasons.append("workflow is event-only or not dispatchable")
            if "automation_task_id" not in {
                item.get("name") for item in workflow.get("inputs", []) if isinstance(item, dict)
            }:
                reasons.append("workflow correlation input is missing")
            if not re.search(r"(?m)^run-name:.*\$\{\{\s*inputs\.automation_task_id\b", content):
                reasons.append("workflow run-name correlation is missing")
            if "main" not in workflow.get("allowed_refs", []):
                reasons.append("main is not an allowlisted dispatch ref")

            sections = workflow_permission_sections(content)
            write_scopes = sorted({
                f"{scope}:write"
                for section in sections for scope, access in section.items()
                if access == "write"
            })
            row["write_scopes"] = write_scopes
            side_effects = []
            for scope in ("contents", "actions", "issues", "pull-requests", "packages", "deployments"):
                if f"{scope}:write" in write_scopes:
                    side_effects.append(f"{scope}_write")
            if re.search(r"(?m)^\s*(?:git\s+push|git\s+commit)\b", content):
                side_effects.append("git_publication")
            if re.search(r"(?m)^\s*gh\s+workflow\s+run\b", content):
                side_effects.append("downstream_workflow_dispatch")
            if re.search(r"(?i)(?:write_text|open\([^)]*['\"]w|tee\s+).*shadowrocket/ss\.conf", content):
                side_effects.append("possible_protected_config_write")
            row["side_effects"] = sorted(set(side_effects))
            if not caller_permissions_ready:
                reasons.append("Watchdog queue job lacks required actions:write and contents:write caller scopes")
            required = workflow.get("caller_permissions_required", [])
            if not all(scope in required for scope in ("actions:write", "contents:write")):
                reasons.append("workflow adapter does not declare both required caller permission scopes")
            if "possible_protected_config_write" in side_effects:
                reasons.append("workflow may write protected shadowrocket/ss.conf")
            row["least_privilege_canary_candidate"] = (
                workflow.get("dispatchable") is True
                and not write_scopes
                and not side_effects
                and caller_permissions_ready
                and "automation_task_id" in {item.get("name") for item in workflow.get("inputs", []) if isinstance(item, dict)}
                and bool(re.search(r"(?m)^run-name:.*\$\{\{\s*inputs\.automation_task_id\b", content))
            )
        else:
            if adapter.get("interface_status") != "reviewed":
                reasons.append("Python interface is not reviewed")
            if not isinstance(adapter.get("input_contract"), dict):
                reasons.append("Python input contract is missing")
            if not isinstance(adapter.get("output_contract"), dict):
                reasons.append("Python output contract is missing")
            if adapter.get("entrypoint", {}).get("shell") is not False:
                reasons.append("Python entrypoint does not explicitly prohibit shell execution")

        row["blockers"] = sorted(set(reasons))
        row["preactivation_ready"] = not row["blockers"]
        rows.append(row)

    canaries = [row["program_id"] for row in rows if row["least_privilege_canary_candidate"]]
    return {
        "schema_version": 1,
        "read_only": True,
        "activation_performed": False,
        "program_count": len(programs),
        "adapter_count": len(adapters),
        "enabled_adapter_count": sum(a.get("enabled") is True for a in adapters),
        "watchdog_caller_permissions": watchdog_permissions,
        "watchdog_caller_permissions_ready": caller_permissions_ready,
        "least_privilege_canary_candidates": canaries,
        "adapters": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--adapters", type=Path)
    args = parser.parse_args()
    try:
        report = audit_activation_readiness(args.root, args.registry, args.adapters)
    except (OSError, ValueError) as exc:
        print(f"ACTIVATION AUDIT ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
