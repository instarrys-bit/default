#!/usr/bin/env python3
"""Fail-closed validation for the unified automation release manifest."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("automation/release_manifest.json")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_COMPONENTS = {
    "program_registry": ("automation/program_registry.json",),
    "execution_adapters": ("automation/execution_adapters.json",),
    "ruleset_manifest": ("rulesets/manifest.json",),
}
EXPECTED_PINS = {
    "watchdog_workflow": ".github/workflows/automation-watchdog.yml",
    "production_workflow": ".github/workflows/auto_sync.yml",
    "config_baseline": "shadowrocket/ss.conf",
}


def _load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise ValueError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _validate_blob_pin(root: Path, path: str, sha: str, label: str) -> None:
    if not isinstance(path, str) or not path or path.startswith("/") or ".." in Path(path).parts:
        raise ValueError(f"{label}.path must be a repository-relative path")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ValueError(f"{label}.git_blob_sha must be a 40-character lowercase Git SHA")
    try:
        object_type = _git(root, "cat-file", "-t", sha)
    except ValueError as exc:
        raise ValueError(f"{label} references a missing Git object {sha}") from exc
    if object_type != "blob":
        raise ValueError(f"{label} must pin a Git blob, got {object_type!r}")
    # A blob existing somewhere in the object database is insufficient: prove
    # that this exact blob belonged to the declared path in reachable history.
    commits = _git(root, "log", "--all", "--format=%H", "--", path).splitlines()
    for commit in commits:
        candidate = subprocess.run(
            ["git", "rev-parse", "--verify", f"{commit}:{path}"],
            cwd=root, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False,
        )
        if candidate.returncode == 0 and candidate.stdout.strip() == sha:
            return
    raise ValueError(f"{label} blob does not match {path} in reachable Git history")


def validate_release_manifest(root: Path = ROOT, manifest_path: Path | None = None) -> dict:
    root = Path(root).resolve()
    path = Path(manifest_path) if manifest_path else root / MANIFEST
    doc = _load_json(path, "release manifest")
    version = doc.get("schema_version")
    if isinstance(version, bool) or version != 1:
        raise ValueError("release manifest schema_version must be 1")
    release_id = doc.get("release_id")
    if not isinstance(release_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{5,100}", release_id):
        raise ValueError("release_id is missing or invalid")
    if doc.get("release_status") != "baseline_snapshot":
        raise ValueError("release_status must be baseline_snapshot")
    created = doc.get("created_on")
    try:
        dt.date.fromisoformat(created)
    except (TypeError, ValueError) as exc:
        raise ValueError("created_on must be an ISO date") from exc
    if not isinstance(doc.get("purpose"), str) or not doc["purpose"].strip():
        raise ValueError("purpose must be a non-empty string")

    components = doc.get("component_schemas")
    if not isinstance(components, dict) or set(components) != set(EXPECTED_COMPONENTS):
        raise ValueError("component_schemas must contain exactly program_registry, execution_adapters, and ruleset_manifest")
    checked = []
    for name, (expected_path,) in EXPECTED_COMPONENTS.items():
        item = components[name]
        if not isinstance(item, dict) or item.get("path") != expected_path:
            raise ValueError(f"component_schemas.{name}.path must be {expected_path}")
        schema = item.get("schema_version")
        if isinstance(schema, bool) or not isinstance(schema, int) or schema < 1:
            raise ValueError(f"component_schemas.{name}.schema_version must be a positive integer")
        _validate_blob_pin(root, item["path"], item.get("git_blob_sha"), f"component_schemas.{name}")
        checked.append(name)

    pins = doc.get("implementation_pins")
    if not isinstance(pins, dict) or not set(EXPECTED_PINS).issubset(pins):
        raise ValueError("implementation_pins is missing a required workflow or config pin")
    for name, expected_path in EXPECTED_PINS.items():
        item = pins[name]
        if not isinstance(item, dict) or item.get("path") != expected_path:
            raise ValueError(f"implementation_pins.{name}.path must be {expected_path}")
        _validate_blob_pin(root, item["path"], item.get("git_blob_sha"), f"implementation_pins.{name}")

    config = pins["config_baseline"]
    if config.get("access") != "read_only":
        raise ValueError("config_baseline access must remain read_only")
    review = pins.get("review_engine")
    if not isinstance(review, dict) or not isinstance(review.get("declared_version"), str) or not review["declared_version"].strip():
        raise ValueError("review_engine.declared_version is required")
    if review.get("source_commit") is not None:
        commit = review["source_commit"]
        if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
            raise ValueError("review_engine.source_commit must be null or a full Git SHA")
        _git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    elif review.get("verification_status") != "declared_in_ruleset_manifest_only":
        raise ValueError("an unpinned review engine must remain explicitly unverified")

    compatibility = doc.get("compatibility")
    if (not isinstance(compatibility, dict)
            or compatibility.get("status") != "not_yet_machine_verified"
            or compatibility.get("unknown_versions_are_blocking") is not True
            or not isinstance(compatibility.get("rule"), str)
            or not compatibility["rule"].strip()):
        raise ValueError("compatibility must remain explicitly unverified and fail closed for unknown versions")

    policy = doc.get("execution_policy")
    required_policy = {
        "new_python_adapters_enabled": False,
        "existing_adapter_enablement_unchanged": True,
        "watchdog_is_top_level_orchestrator": True,
        "dashboard_is_read_only_observer": True,
        "production_may_not_write_config_baseline": True,
        "ruleset_writers_require_resource_exclusive_lease": True,
        "reject_rule_publication_requires_explicit_approval": True,
    }
    if not isinstance(policy, dict):
        raise ValueError("execution_policy must be an object")
    for key, expected in required_policy.items():
        if policy.get(key) is not expected:
            raise ValueError(f"execution_policy.{key} must be {expected!r}")

    adapters_path = root / "automation/execution_adapters.json"
    adapters_doc = _load_json(adapters_path, "execution adapters")
    adapters = adapters_doc.get("adapters")
    if not isinstance(adapters, list):
        raise ValueError("execution adapters must contain an adapters array")
    enabled_python = [
        item.get("target_program_id", "<unknown>")
        for item in adapters
        if isinstance(item, dict) and item.get("target_kind") == "python_component" and item.get("enabled") is True
    ]
    if enabled_python:
        raise ValueError("Python adapters must remain disabled: " + ", ".join(enabled_python))

    gaps = doc.get("known_gaps")
    if not isinstance(gaps, list) or not gaps or any(not isinstance(x, str) or not x.strip() for x in gaps):
        raise ValueError("known_gaps must be a non-empty array of descriptions")
    migration = doc.get("next_migration_gate")
    if not isinstance(migration, dict) or not isinstance(migration.get("required_before_independent_python_dispatch"), list):
        raise ValueError("next_migration_gate requirements are missing")
    if migration.get("completion_status") != "blocked_pending_contract_and_runtime_enforcement":
        raise ValueError("independent Python dispatch must remain blocked pending contract/runtime enforcement")

    return {
        "valid": True,
        "release_id": release_id,
        "schema_version": version,
        "verified_git_blob_pins": len(checked) + len(EXPECTED_PINS),
        "python_adapters_enabled": 0,
        "independent_python_dispatch": "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    try:
        result = validate_release_manifest(args.root, args.manifest)
    except ValueError as exc:
        print(f"RELEASE MANIFEST INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
