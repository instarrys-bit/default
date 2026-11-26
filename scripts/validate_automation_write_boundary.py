#!/usr/bin/env python3
"""Validate rulesets-only production writes and the authorized metadata-only uu.conf baseline writer."""
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
}
BASELINE_WRITER = "Storage Management / File Management"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def validate_write_boundary(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    storage = (root / ".github/workflows/storage-management.yml").read_text(encoding="utf-8")
    production = (root / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
    baseline_script = (root / "scripts/register_config_baseline.py").read_text(encoding="utf-8")
    publisher_path = root / "scripts/publish_config_baseline_metadata.sh"
    publisher = publisher_path.read_text(encoding="utf-8") if publisher_path.exists() else ""
    policy = json.loads((root / "sources/policy.json").read_text(encoding="utf-8"))
    release = json.loads((root / "automation/release_manifest.json").read_text(encoding="utf-8"))
    write_sets = json.loads((root / "automation/resource_write_sets.json").read_text(encoding="utf-8"))

    if "reconcile-config-baseline:" not in storage:
        errors.append("Storage Management does not declare the metadata-only baseline reconciliation job")
    if "python3 scripts/register_config_baseline.py --apply" not in storage or "bash scripts/publish_config_baseline_metadata.sh" not in storage:
        errors.append("Storage Management does not invoke both guarded metadata preparation and publication")
    if "fetch-depth: 0" not in storage or "contents: write" not in storage:
        errors.append("Storage Management baseline writer lacks full history or contents:write permission")
    if "--apply" not in baseline_script or "owner_approved_config_history" not in baseline_script:
        errors.append("Baseline metadata writer lacks explicit apply mode or owner-history verification")
    if "config.read_bytes() != config_bytes" not in baseline_script or "ALLOWLIST" not in baseline_script:
        errors.append("Baseline metadata writer does not verify config byte immutability and an exact allowlist")
    if not publisher or "git add --" not in publisher or "git push origin HEAD:main" not in publisher:
        errors.append("Metadata publisher lacks exact staging or non-force main publication")
    for marker in (
        'expected="sources/policy.json automation/release_manifest.json automation/production_workflow_map.json automation/resource_write_sets.json"',
        "Unexpected modified or untracked paths",
        "Unexpected staged paths",
        "Protected modules/uu.conf is staged; refusing to commit.",
        'git rev-parse HEAD:modules/uu.conf',
        'git rev-parse origin/main:modules/uu.conf',
    ):
        if marker not in publisher:
            errors.append(f"Metadata publisher is missing required safety fence: {marker}")

    required_production_guards = (
        "rulesets/*)",
        "Refusing non-ruleset repository write",
        "Protected config modules/uu.conf is staged; refusing to commit.",
    )
    for marker in required_production_guards:
        if marker not in production:
            errors.append(f"Production publisher is missing required write fence: {marker}")

    guard = policy.get("managed_config_guard", {})
    if guard.get("path") != "modules/uu.conf" or guard.get("content_immutable_to_automation") is not True:
        errors.append("modules/uu.conf must remain the immutable managed config")
    content = guard.get("content_protection", {})
    if content.get("automation_may_modify_content") is not False or content.get("production_automation_may_edit_content") is not False:
        errors.append("no automation may modify modules/uu.conf content")
    if content.get("baseline_metadata_registration_may_edit_content") is not False:
        errors.append("baseline metadata registration must never edit modules/uu.conf content")

    approved_sha = guard.get("approved_git_blob_sha")
    if not isinstance(approved_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", approved_sha):
        errors.append("sources/policy.json must retain a valid approved uu.conf Git blob")
    metadata_policy = guard.get("baseline_metadata_policy", {})
    for key in (
        "automation_may_update_registered_blob_sha",
        "automation_may_update_release_baseline_sha",
        "automation_may_update_approved_baseline_sha",
    ):
        if metadata_policy.get(key) is not True:
            errors.append(f"baseline metadata policy must explicitly authorize {key}")
    if metadata_policy.get("owner_authored_config_history_required") is not True:
        errors.append("automatic baseline metadata sync must verify all intervening owner-authored config commits")
    if metadata_policy.get("reviewed_pr_required") is not True:
        errors.append("manual baseline metadata PRs must still require human review")
    if set(metadata_policy.get("metadata_write_allowlist", [])) != BASELINE_ALLOWLIST:
        errors.append("policy baseline metadata allowlist is not the exact four-path set")
    if metadata_policy.get("registration_must_not_write_config_content") is not True:
        errors.append("baseline registration must explicitly prohibit config-content writes")

    pin = release.get("implementation_pins", {}).get("config_baseline", {})
    if pin.get("path") != "modules/uu.conf" or pin.get("access") != "read_only" or pin.get("git_blob_sha") != approved_sha:
        errors.append("release manifest must pin the same read-only approved uu.conf baseline")
    release_sync = release.get("execution_policy", {}).get("watchdog_baseline_metadata_sync", {})
    if (release_sync.get("writer") != BASELINE_WRITER
            or release_sync.get("trigger") != ["push", "schedule"]
            or set(release_sync.get("write_allowlist", [])) != BASELINE_ALLOWLIST
            or release_sync.get("protected_config") != "modules/uu.conf is byte-for-byte read-only to automation."):
        errors.append("release manifest metadata-only writer contract is invalid")

    protected = write_sets.get("policy", {}).get("protected_config", {})
    if protected.get("path") != "modules/uu.conf" or protected.get("access") != "read_only":
        errors.append("resource write inventory does not mark uu.conf read-only")
    if protected.get("writers_allowed") != []:
        errors.append("resource write inventory grants a writer for uu.conf content")
    sync = protected.get("metadata_only_sync", {})
    if sync.get("writer") != BASELINE_WRITER or set(sync.get("allowed_paths", [])) != BASELINE_ALLOWLIST:
        errors.append("resource write inventory metadata-only writer allowlist is invalid")
    if sync.get("never_write") != ["modules/uu.conf"]:
        errors.append("resource write inventory must explicitly forbid uu.conf content writes")
    if BASELINE_ALLOWLIST & {"modules/uu.conf"}:
        errors.append("protected config path must never appear in the metadata allowlist")

    return errors


def main() -> int:
    errors = validate_write_boundary()
    if errors:
        for error in errors:
            print("AUTOMATION WRITE BOUNDARY INVALID: " + error, file=sys.stderr)
        return 1
    policy = json.loads((ROOT / "sources/policy.json").read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    approved_sha = guard["approved_git_blob_sha"]
    observed_sha = git_blob_sha((ROOT / "modules/uu.conf").read_bytes())
    print(json.dumps({
        "valid": True,
        "production_write_scope": "rulesets/**",
        "baseline_metadata_writer": BASELINE_WRITER,
        "baseline_metadata_allowlist": sorted(BASELINE_ALLOWLIST),
        "protected_config": "modules/uu.conf",
        "observed_config_git_blob_sha": observed_sha,
        "approved_baseline_matches_observed": approved_sha == observed_sha,
        "config_content_write_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
