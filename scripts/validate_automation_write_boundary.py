#!/usr/bin/env python3
"""Fail-closed guard for rulesets-only publication and reviewed-PR config baselines."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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

    if "reconcile-config-baseline:" in storage:
        errors.append("Storage Management still declares an automatic config-baseline job")
    if "register_config_baseline.py --apply" in storage or "publish_config_baseline_metadata.sh" in storage:
        errors.append("Storage Management still invokes an automatic baseline metadata writer")
    if re.search(r"(?m)^\s*git\s+(?:commit|push)\b", storage):
        errors.append("Storage Management contains a direct Git repository writer")
    if "python3 scripts/verify_baseline.py --verify-registration" not in storage:
        errors.append("Storage Management CI does not verify reviewed baseline metadata PRs")
    if "--apply" in baseline_script or "def apply_baseline_updates(" in baseline_script:
        errors.append("Baseline proposal tool still exposes repository-write capability")
    if "RUNNER_TEMP" not in baseline_script or "write_baseline_proposal" not in baseline_script:
        errors.append("Baseline proposal tool is not confined to runner-local proposal output")
    write_calls = re.findall(r"\.write_text\s*\(", baseline_script)
    if len(write_calls) != 1 or "destination.write_text(" not in baseline_script:
        errors.append("Baseline proposal tool writes outside its single runner-local destination")
    if "git push" in publisher or "git commit" in publisher or "git add" in publisher:
        errors.append("Retired baseline publisher still contains repository-write commands")
    if publisher and "Disabled:" not in publisher:
        errors.append("Retired baseline publisher is not fail-closed")

    required_publisher_guards = (
        "rulesets/*)",
        "Refusing non-ruleset repository write",
        "Protected config modules/uu.conf is staged; refusing to commit.",
    "python3 scripts/verify_baseline.py --verify-registration",
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
    if actual_sha != approved_sha:
        errors.append("sources/policy.json does not pin the current modules/uu.conf Git blob")

    metadata_policy = guard.get("baseline_metadata_policy", {})
    for key in (
        "automation_may_update_registered_blob_sha",
        "automation_may_update_release_baseline_sha",
        "automation_may_update_approved_baseline_sha",
    ):
        if metadata_policy.get(key) is not False:
            errors.append(f"baseline metadata policy must deny {key}")
    if metadata_policy.get("reviewed_pr_required") is not True:
        errors.append("baseline metadata changes must require a separately reviewed pull request")
    if metadata_policy.get("proposal_generation_mode") != "runner_local_only":
        errors.append("baseline proposal generation must remain runner-local")

    pin = release.get("implementation_pins", {}).get("config_baseline", {})
    if (pin.get("path") != "modules/uu.conf" or pin.get("access") != "read_only"
            or pin.get("git_blob_sha") != approved_sha):
        errors.append("release manifest must pin the same read-only uu.conf baseline")

    release_sync = release.get("execution_policy", {}).get("watchdog_baseline_metadata_sync", {})
    if release_sync.get("writer") is not None or release_sync.get("trigger") != [] or release_sync.get("write_allowlist") != []:
        errors.append("release manifest authorizes an automated baseline metadata writer")

    protected = write_sets.get("policy", {}).get("protected_config", {})
    if protected.get("path") != "modules/uu.conf" or protected.get("access") != "read_only":
        errors.append("resource write inventory does not mark uu.conf read-only")
    if protected.get("writers_allowed") != []:
        errors.append("resource write inventory grants a writer for uu.conf")
    sync = protected.get("metadata_only_sync", {})
    if sync.get("writer") is not None or sync.get("allowed_paths") != []:
        errors.append("resource write inventory authorizes automated baseline metadata writes")
    if sync.get("never_write") != ["modules/uu.conf"]:
        errors.append("resource write inventory must explicitly forbid uu.conf content writes")

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
        "baseline_metadata_writer": None,
        "baseline_proposal_scope": "RUNNER_TEMP only",
        "baseline_metadata_changes": "separately_reviewed_pull_request_required",
        "protected_config": "modules/uu.conf",
        "observed_config_git_blob_sha": observed_config_sha,
        "approved_baseline_matches_observed": approved_sha == observed_config_sha,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
