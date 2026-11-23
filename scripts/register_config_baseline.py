#!/usr/bin/env python3
"""Automatically follow the latest main-branch uu.conf blob by updating metadata only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from audit_config_drift import build_report

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = "modules/uu.conf"
ALLOWLIST = (
    "sources/policy.json",
    "automation/release_manifest.json",
    "automation/production_workflow_map.json",
    "automation/resource_write_sets.json",
    "reports/config-drift-audit.json",
)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def run(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(args, cwd=ROOT, check=check, capture_output=True, text=True)
    return result.stdout.strip()


def config_change_history(guard: dict) -> list[str]:
    """Return config-changing commits for evidence; author identity never blocks SHA registration."""
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        return []
    head = run(["git", "rev-parse", "HEAD"])
    anchor = str(guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if len(anchor) == 40:
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", anchor, head],
            cwd=ROOT,
            capture_output=True,
        )
        if ancestry.returncode == 0:
            commits = run(["git", "rev-list", f"{anchor}..{head}", "--", CONFIG_PATH]).splitlines()
            return [item for item in commits if item]
    latest = run(["git", "log", "-1", "--format=%H", "HEAD", "--", CONFIG_PATH], check=False)
    return [latest] if latest else [head]


def json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def prepare_metadata(actual: str, previous: str, commits: list[str]) -> dict[str, str]:
    policy_path = ROOT / "sources/policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    if guard.get("path") != CONFIG_PATH or guard.get("content_immutable_to_automation") is not True:
        raise ValueError("managed config protection invariant is invalid")
    actor = os.environ.get("GITHUB_ACTOR", "github-actions[bot]")
    now = datetime.now(timezone.utc).isoformat()
    guard["approved_git_blob_sha"] = actual
    guard["last_user_approved_baseline_update"] = {
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "reason": "User-authorized automatic SHA follow on the latest stable main revision, independent of commit author attribution. Only baseline metadata and derived release pins are updated; uu.conf bytes are immutable to automation.",
        "approval_mode": "user_authorized_automatic_sha_follow",
        "config_change_commits": commits,
        "actor": actor,
        "commit_sha": commits[0],
        "registered_at": now,
    }

    release_path = ROOT / "automation/release_manifest.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    pin = release["implementation_pins"]["config_baseline"]
    if pin.get("path") != CONFIG_PATH or pin.get("access") != "read_only":
        raise ValueError("release manifest config pin is not read-only modules/uu.conf")
    pin["git_blob_sha"] = actual
    for key, path in (
        ("baseline_registration_runtime", "scripts/register_config_baseline.py"),
        ("automation_write_boundary_validator", "scripts/validate_automation_write_boundary.py"),
        ("storage_management_workflow", ".github/workflows/storage-management.yml"),
        ("baseline_metadata_publisher", "scripts/publish_config_baseline_metadata.sh"),
    ):
        if key in release.get("implementation_pins", {}):
            release["implementation_pins"][key]["git_blob_sha"] = run(["git", "rev-parse", f"HEAD:{path}"])
    release_text = json_text(release)
    release_sha = git_blob_sha(release_text.encode("utf-8"))

    workflow_map_path = ROOT / "automation/production_workflow_map.json"
    workflow_map = json.loads(workflow_map_path.read_text(encoding="utf-8"))
    workflow_map["review_context"]["release_manifest_blob_sha"] = release_sha

    write_sets_path = ROOT / "automation/resource_write_sets.json"
    write_sets = json.loads(write_sets_path.read_text(encoding="utf-8"))
    write_sets["review_context"]["release_manifest_blob_sha"] = release_sha

    report_path = ROOT / "reports/config-drift-audit.json"
    config_bytes = (ROOT / CONFIG_PATH).read_bytes()
    report = build_report(config_bytes, actual, CONFIG_PATH, policy.get("dns_invariants", {}))
    report["owner_approved_change_pending_registration"] = False
    report["registration"] = {
        "status": "registered",
        "registered_at": now,
        "config_change_commits": commits,
        "writer": "Storage Management / File Management",
        "config_content_modified": False,
    }

    return {
        "sources/policy.json": json_text(policy),
        "automation/release_manifest.json": release_text,
        "automation/production_workflow_map.json": json_text(workflow_map),
        "automation/resource_write_sets.json": json_text(write_sets),
        "reports/config-drift-audit.json": json_text(report),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write only the explicit metadata allowlist in the checkout")
    args = parser.parse_args()
    policy = json.loads((ROOT / "sources/policy.json").read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    if guard.get("path") != CONFIG_PATH or guard.get("content_immutable_to_automation") is not True:
        raise ValueError("uu.conf must remain the immutable managed config")
    config = ROOT / CONFIG_PATH
    original = config.read_bytes()
    actual = git_blob_sha(original)
    previous = str(guard["approved_git_blob_sha"])
    if actual == previous:
        report_path = ROOT / "reports/config-drift-audit.json"
        report = build_report(original, previous, CONFIG_PATH, policy.get("dns_invariants", {}))
        report["owner_approved_change_pending_registration"] = False
        update = guard.get("last_user_approved_baseline_update", {})
        report["registration"] = {
            "status": "registered",
            "registered_at": update.get("registered_at"),
            "config_change_commits": update.get("config_change_commits", []),
            "writer": "Storage Management / File Management",
            "config_content_modified": False,
        }
        changed_report = report != json.loads(report_path.read_text(encoding="utf-8"))
        if changed_report and args.apply:
            report_path.write_text(json_text(report), encoding="utf-8")
        print(json.dumps({"status": "audit_report_refreshed" if changed_report and args.apply else "no_change", "blob_sha": actual, "audit_report_refresh_needed": changed_report, "config_content_modified": False}, sort_keys=True))
        return 0

    commits = config_change_history(guard)
    if not commits:
        commits = [run(["git", "rev-parse", "HEAD"])]

    if not args.apply:
        print(json.dumps({"status": "automatic_sha_follow_ready", "previous_blob_sha": previous, "new_blob_sha": actual, "verified_commits": commits, "config_content_modified": False}, sort_keys=True))
        return 0

    updates = prepare_metadata(actual, previous, commits)
    for relative, content in updates.items():
        if relative not in ALLOWLIST:
            raise ValueError(f"refusing non-allowlisted metadata path: {relative}")
        (ROOT / relative).write_text(content, encoding="utf-8")
    if config.read_bytes() != original:
        raise RuntimeError("protected modules/uu.conf bytes changed during metadata registration")
    changed = sorted(run(["git", "diff", "--name-only"]).splitlines())
    if changed and any(path not in ALLOWLIST for path in changed):
        raise RuntimeError(f"unexpected modified path outside metadata allowlist: {changed}")
    print(json.dumps({
        "status": "metadata_registered_pending_git_commit",
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "config_change_commits": commits,
        "modified_paths": changed,
        "config_content_modified": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError, RuntimeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
