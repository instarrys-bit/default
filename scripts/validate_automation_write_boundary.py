#!/usr/bin/env python3
"""Validate ruleset-only production writes and File Management metadata-only baseline writes."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_ALLOWLIST = {
    "sources/policy.json",
    "automation/release_manifest.json",
    "automation/production_workflow_map.json",
    "automation/resource_write_sets.json",
    "reports/config-drift-audit.json",
}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def validate_write_boundary(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    storage = (root / ".github/workflows/storage-management.yml").read_text(encoding="utf-8")
    production = (root / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
    baseline_script = (root / "scripts/register_config_baseline.py").read_text(encoding="utf-8")
    policy = json.loads((root / "sources/policy.json").read_text(encoding="utf-8"))
    release = json.loads((root / "automation/release_manifest.json").read_text(encoding="utf-8"))
    write_sets = json.loads((root / "automation/resource_write_sets.json").read_text(encoding="utf-8"))

    if "register_config_baseline.py --apply" not in storage:
        errors.append("Storage Management does not execute the baseline metadata registration writer")
    publisher_path = root / "scripts/publish_config_baseline_metadata.sh"
    if "fetch-depth: 0" not in storage or "bash scripts/publish_config_baseline_metadata.sh" not in storage:
        errors.append("Storage Management lacks full-history checkout or the guarded metadata publisher")
    if not publisher_path.exists():
        errors.append("the dedicated baseline metadata publisher is missing")
    else:
        publisher = publisher_path.read_text(encoding="utf-8")
        if "git push origin HEAD:main" not in publisher or "modules/uu.conf" not in publisher:
            errors.append("baseline metadata publisher lacks guarded publication or protected-config checks")
    if "BASELINE_METADATA_ALLOWLIST" not in storage:
        errors.append("Storage Management does not declare the explicit metadata-only write allowlist")
    if "--apply" not in baseline_script or "CONFIG_PATH = \"modules/uu.conf\"" not in baseline_script:
        errors.append("Baseline registration script is not wired for explicit apply mode")
    if "config.read_bytes() != original" not in baseline_script:
        errors.append("Baseline registration does not verify uu.conf byte immutability")

    required_publisher_guards = (
        "rulesets/*)",
        "Refusing non-ruleset repository write",
        "Protected config modules/uu.conf is staged; refusing to commit.",
    )
    for marker in required_publisher_guards:
        if marker not in production:
            errors.append(f"Production publisher is missing required write fence: {marker}")

    guard = policy.get("managed_config_guard", {})
    if guard.get("path") != "modules/uu.conf" or guard.get("content_immutable_to_automation") is not True:
        errors.append("modules/uu.conf must remain the immutable managed config")
    actual_sha = git_blob_sha((root / "modules/uu.conf").read_bytes())
    approved_sha = guard.get("approved_git_blob_sha")
    if not isinstance(approved_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", approved_sha):
        errors.append("sources/policy.json must retain a valid approved uu.conf Git blob")
    pin = release.get("implementation_pins", {}).get("config_baseline", {})
    if (pin.get("path") != "modules/uu.conf" or pin.get("access") != "read_only"
            or pin.get("git_blob_sha") != approved_sha):
        errors.append("release manifest must pin the same read-only uu.conf baseline")

    protected = write_sets.get("policy", {}).get("protected_config", {})
    if protected.get("path") != "modules/uu.conf" or protected.get("access") != "read_only":
        errors.append("resource write inventory does not mark uu.conf read-only")
    if protected.get("writers_allowed") != []:
        errors.append("resource write inventory grants a writer for uu.conf")
    sync = protected.get("metadata_only_sync", {})
    if sync.get("writer") != "Storage Management / File Management":
        errors.append("only Storage Management / File Management may write baseline metadata")
    if set(sync.get("allowed_paths", [])) != BASELINE_ALLOWLIST:
        errors.append("baseline metadata writer allowlist does not match the approved five paths")
    if sync.get("never_write") != ["modules/uu.conf"]:
        errors.append("metadata writer must explicitly forbid uu.conf content writes")

    release_sync = release.get("execution_policy", {}).get("watchdog_baseline_metadata_sync", {})
    if release_sync.get("writer") != "Storage Management / File Management":
        errors.append("release manifest does not identify File Management as the baseline metadata writer")
    if set(release_sync.get("write_allowlist", [])) != BASELINE_ALLOWLIST:
        errors.append("release manifest baseline metadata allowlist is inconsistent")
    if release_sync.get("protected_config") != "modules/uu.conf is byte-for-byte read-only to automation.":
        errors.append("release manifest does not preserve the byte-for-byte uu.conf protection")
    if actual_sha != approved_sha:
        # Drift is observed and tracked, never silently written into uu.conf.
        if not (root / "reports/config-drift-audit.json").exists():
            errors.append("config drift report is missing while observed SHA differs from registered baseline")
    return errors


def main() -> int:
    errors = validate_write_boundary()
    if errors:
        for error in errors:
            print("AUTOMATION WRITE BOUNDARY INVALID: " + error, file=sys.stderr)
        return 1
    policy = json.loads((ROOT / "sources/policy.json").read_text(encoding="utf-8"))
    approved_sha = policy["managed_config_guard"]["approved_git_blob_sha"]
    observed_config_sha = git_blob_sha((ROOT / "modules/uu.conf").read_bytes())
    print(json.dumps({
        "valid": True,
        "production_write_scope": "rulesets/**",
        "baseline_metadata_writer": "Storage Management / File Management",
        "baseline_metadata_allowlist": sorted(BASELINE_ALLOWLIST),
        "protected_config": "modules/uu.conf",
        "observed_config_git_blob_sha": observed_config_sha,
        "approved_baseline_matches_observed": approved_sha == observed_config_sha,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
