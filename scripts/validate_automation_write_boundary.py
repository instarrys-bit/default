#!/usr/bin/env python3
"""Fail-closed guard for production publication and the protected uu.conf baseline."""
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
    policy = json.loads((root / "sources/policy.json").read_text(encoding="utf-8"))
    release = json.loads((root / "automation/release_manifest.json").read_text(encoding="utf-8"))
    write_sets = json.loads((root / "automation/resource_write_sets.json").read_text(encoding="utf-8"))

    if "git push origin HEAD:main" in storage or "git commit " in storage:
        errors.append("Storage Management still declares an automated baseline reconciliation writer")
    if "register_config_baseline.py --apply" in storage:
        errors.append("Storage Management invokes the forbidden baseline apply mode")
    if re.search(r"(?m)^\s*git\s+(?:commit|push)\b", storage):
        errors.append("Storage Management contains a direct Git repository writer")
    if "--apply" in baseline_script or "def apply_baseline_updates(" in baseline_script:
        errors.append("Baseline registration still exposes repository write capability")

    required_publisher_guards = (
        "rulesets/*)",
        "Refusing non-ruleset repository write",
        "Protected config modules/uu.conf is staged; refusing to commit.",
    )
    for marker in required_publisher_guards:
        if marker not in production:
            errors.append(f"Production publisher is missing required write fence: {marker}")

    guard = policy.get("managed_config_guard", {})
    if guard.get("path") != "modules/uu.conf":
        errors.append("Managed config identity must remain modules/uu.conf")
    if guard.get("content_immutable_to_automation") is not True:
        errors.append("Managed config must remain immutable to automation")
    actual_sha = git_blob_sha((root / "modules/uu.conf").read_bytes())
    approved_sha = guard.get("approved_git_blob_sha")
    if not isinstance(approved_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", approved_sha):
        errors.append("sources/policy.json must retain a valid historical approved uu.conf Git blob")
    pin = release.get("implementation_pins", {}).get("config_baseline", {})
    if (pin.get("path") != "modules/uu.conf"
            or pin.get("access") != "read_only"
            or not isinstance(pin.get("git_blob_sha"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", pin.get("git_blob_sha", ""))
            or pin.get("git_blob_sha") != approved_sha):
        errors.append("release manifest must retain the read-only historical approved uu.conf baseline pin")

    # Current content drift is an observation, not a write-boundary violation.
    # Storage Management durably records the observed blob SHA in its integrity
    # projection; approval pins remain historical until a separately reviewed
    # metadata change. Never rewrite uu.conf or silently advance its approval.
    observed_config_sha = actual_sha

    protected = write_sets.get("policy", {}).get("protected_config", {})
    if protected.get("path") != "modules/uu.conf" or protected.get("access") != "read_only":
        errors.append("resource write inventory does not mark uu.conf read-only")
    if protected.get("writers_allowed") != []:
        errors.append("resource write inventory grants a writer for uu.conf")
    sync = protected.get("metadata_only_sync", {})
    if sync.get("writer") is not None or sync.get("allowed_paths") != []:
        errors.append("resource write inventory authorizes automated baseline metadata writes")
    return errors


def main() -> int:
    errors = validate_write_boundary()
    if errors:
        for error in errors:
            print("AUTOMATION WRITE BOUNDARY INVALID: " + error, file=sys.stderr)
        return 1
    policy = json.loads((ROOT / "sources" / "policy.json").read_text(encoding="utf-8"))
    approved_sha = policy["managed_config_guard"]["approved_git_blob_sha"]
    observed_config_sha = git_blob_sha((ROOT / "modules" / "uu.conf").read_bytes())
    print(json.dumps({
        "valid": True,
        "production_write_scope": "rulesets/**",
        "protected_config": "modules/uu.conf",
        "observed_config_git_blob_sha": observed_config_sha,
        "approved_baseline_matches_observed": approved_sha == observed_config_sha,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
