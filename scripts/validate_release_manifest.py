#!/usr/bin/env python3
"""Fail-closed validation for the unified automation release manifest."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()


import argparse
import datetime as dt
import hashlib
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
    "config_baseline": "modules/uu.conf",
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


def _canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_python_adapter_policy(root: Path, policy: object,
                                    adapters_doc: dict, registry_doc: dict,
                                    release_id: str) -> int:
    if not isinstance(policy, dict) or policy.get("schema_version") != 1:
        raise ValueError("python_adapter_policy schema_version must be 1")
    if policy.get("default_decision") != "deny":
        raise ValueError("python_adapter_policy default_decision must be deny")
    records = policy.get("allowed_adapters")
    if not isinstance(records, list):
        raise ValueError("python_adapter_policy.allowed_adapters must be an array")
    required_fields = {
        "target_program_id", "capability", "release_id", "adapter_entry_sha256",
        "registry_entry_sha256", "source_path", "source_git_blob_sha",
        "allowed_callers", "input_contract_sha256", "output_contract_sha256",
        "dependency_contract_sha256", "resource_contract_sha256",
        "verifier_contract_sha256",
    }
    programs = registry_doc.get("programs")
    adapters = adapters_doc.get("adapters")
    if not isinstance(programs, list) or not isinstance(adapters, list):
        raise ValueError("Python adapter policy requires valid registry and adapter arrays")
    by_program = {item.get("id"): item for item in programs if isinstance(item, dict)}
    by_target = {}
    for item in adapters:
        if isinstance(item, dict) and item.get("target_kind") == "python_component":
            target = item.get("target_program_id")
            if not isinstance(target, str) or not target or target in by_target:
                raise ValueError("Python adapter target IDs must be unique")
            by_target[target] = item

    indexed = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != required_fields:
            raise ValueError("each Python adapter allowlist record must contain exactly the reviewed pin fields")
        target_id = record.get("target_program_id")
        if not isinstance(target_id, str) or not target_id or target_id in indexed:
            raise ValueError("Python adapter allowlist target IDs must be unique non-empty strings")
        indexed[target_id] = record
        adapter = by_target.get(target_id)
        program = by_program.get(target_id)
        if not isinstance(adapter, dict) or not isinstance(program, dict):
            raise ValueError(f"allowlisted Python adapter is not present in registry and adapter inventory: {target_id}")
        if record.get("release_id") != release_id:
            raise ValueError(f"{target_id} release_id does not match the current release")
        capabilities = program.get("capabilities")
        capability = record.get("capability")
        if not isinstance(capabilities, list) or capability not in capabilities:
            raise ValueError(f"{target_id} allowlisted capability is not declared by its registry entry")
        if record["adapter_entry_sha256"] != _canonical_digest(adapter):
            raise ValueError(f"{target_id} adapter entry digest does not match the current adapter")
        if record["registry_entry_sha256"] != _canonical_digest(program):
            raise ValueError(f"{target_id} registry entry digest does not match the current registry")
        entrypoint = adapter.get("entrypoint")
        source_path = record.get("source_path")
        if (not isinstance(entrypoint, dict) or source_path != entrypoint.get("path")
                or source_path != program.get("path") or not isinstance(source_path, str)
                or source_path.startswith("/") or ".." in Path(source_path).parts
                or Path(source_path).is_absolute()):
            raise ValueError(f"{target_id} source path does not match a safe relative adapter entrypoint and registry path")
        if record["source_git_blob_sha"] != _git(root, "hash-object", source_path):
            raise ValueError(f"{target_id} source blob pin does not match the current entrypoint")
        _validate_blob_pin(root, source_path, record["source_git_blob_sha"], f"{target_id}.source")
        callers = record.get("allowed_callers")
        orchestration = program.get("orchestration", {})
        if (not isinstance(orchestration, dict)
                or not isinstance(callers, list) or not callers
                or any(not isinstance(caller, str) or not caller for caller in callers)
                or callers != sorted(set(callers))
                or callers != sorted(adapter.get("allowed_callers", []))
                or callers != sorted(orchestration.get("allowed_callers", []))):
            raise ValueError(f"{target_id} caller allowlist does not match adapter and registry")
        digest_fields = {
            "input_contract_sha256": adapter.get("input_contract"),
            "output_contract_sha256": adapter.get("output_contract"),
            "dependency_contract_sha256": adapter.get("dependency_contract"),
            "resource_contract_sha256": adapter.get("resource_contract"),
            "verifier_contract_sha256": adapter.get("completion", {}).get("artifact_verifier")
                if isinstance(adapter.get("completion"), dict) else None,
        }
        for field, value in digest_fields.items():
            if record.get(field) != _canonical_digest(value):
                raise ValueError(f"{target_id} {field} does not match the current contract")
        if (adapter.get("enabled") is not True or adapter.get("interface_status") != "reviewed"
                or adapter.get("adapter_type") != "python_cli"
                or orchestration.get("enabled") is not True):
            raise ValueError(f"{target_id} is allowlisted but its Python CLI interface or orchestration is not enabled and reviewed")
        if (entrypoint.get("executable") != "python3" or entrypoint.get("shell") is not False
                or not isinstance(entrypoint.get("argv_template"), list)):
            raise ValueError(f"{target_id} entrypoint must use python3 without a shell and declare argv_template")
        for field in ("input_contract", "output_contract", "resource_contract"):
            if not isinstance(adapter.get(field), dict):
                raise ValueError(f"{target_id} requires a reviewed {field}")
        resource = adapter["resource_contract"]
        keys = resource.get("resource_keys")
        lease_seconds = resource.get("lease_seconds")
        if (resource.get("mode") != "exclusive" or resource.get("fencing_required") is not True
                or not isinstance(keys, list) or not keys
                or any(not isinstance(key, str) or not key for key in keys)
                or len(keys) != len(set(keys))
                or isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int)
                or not 1 <= lease_seconds <= 21600):
            raise ValueError(f"{target_id} resource contract must declare unique exclusive fenced keys and a bounded lease")
        write_resources = adapter.get("write_resources", [])
        publish_resources = adapter.get("publish_resources", [])
        if (not isinstance(write_resources, list)
                or any(not isinstance(path, str) or not path for path in write_resources)
                or len(write_resources) != len(set(write_resources))
                or not isinstance(publish_resources, list)
                or any(not isinstance(path, str) or not path for path in publish_resources)
                or len(publish_resources) != len(set(publish_resources))
                or any(path not in keys or path == "modules/uu.conf" for path in write_resources)
                or any(path not in write_resources for path in publish_resources)):
            raise ValueError(f"{target_id} write and publish paths must be nested within fenced resources and exclude the config baseline")
        dependency = adapter.get("dependency_contract")
        if dependency is not None:
            predecessor = dependency.get("predecessor_program_id") if isinstance(dependency, dict) else None
            if (not isinstance(predecessor, str) or predecessor not in by_program
                    or predecessor not in program.get("depends_on", [])
                    or not isinstance(dependency.get("artifact_path"), str)
                    or not isinstance(dependency.get("producer_workflow_name"), str)
                    or dependency.get("edge_type") != "intended_successful_workflow_run_with_immutable_artifact_digest"
                    or not isinstance(dependency.get("enforcement"), str)
                    or not dependency["enforcement"].strip()):
                raise ValueError(f"{target_id} dependency contract must bind a registered typed predecessor and immutable workflow evidence")
        completion = adapter.get("completion")
        verifier = digest_fields["verifier_contract_sha256"]
        if (not isinstance(completion, dict) or completion.get("independent_verification_required") is not True
                or not isinstance(verifier, dict)):
            raise ValueError(f"{target_id} requires an independent artifact verifier contract")
        verifier_program = by_program.get(verifier.get("program_id"))
        if (not isinstance(verifier_program, dict) or verifier_program.get("path") != verifier.get("path")
                or verifier_program.get("kind") != "python_component"):
            raise ValueError(f"{target_id} verifier identity must match a registered Python component")
        if any(caller not in by_program for caller in callers):
            raise ValueError(f"{target_id} caller allowlist contains an unregistered program")

    enabled = {
        target_id for target_id, adapter in by_target.items()
        if adapter.get("enabled") is True
    }
    if enabled != set(indexed):
        missing = sorted(enabled - set(indexed))
        stale = sorted(set(indexed) - enabled)
        raise ValueError("enabled Python adapters and exact release allowlist differ; missing="
                         + ",".join(missing) + "; not_enabled=" + ",".join(stale))
    return len(enabled)


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
        "python_adapter_default_deny": True,
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
    registry_doc = _load_json(root / "automation/program_registry.json", "program registry")
    enabled_python = _validate_python_adapter_policy(
        root, doc.get("python_adapter_policy"), adapters_doc, registry_doc, release_id,
    )

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
        "python_adapters_enabled": enabled_python,
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
