#!/usr/bin/env python3
"""Register owner-authored uu.conf changes by updating metadata only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def owner_approved_config_history(guard: dict) -> list[str]:
    """Return every uu.conf-changing commit since the registered owner anchor, iff all are owner-authored."""
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("GITHUB_REF", "")
    if not owner or not repo or ref != "refs/heads/main":
        return []
    anchor = str(guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if len(anchor) != 40:
        return []
    head = run(["git", "rev-parse", "HEAD"])
    ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", anchor, head], cwd=ROOT)
    if ancestry.returncode != 0:
        return []
    commits = run(["git", "rev-list", "--reverse", f"{anchor}..{head}", "--", CONFIG_PATH]).splitlines()
    commits = [item for item in commits if item]
    if not commits:
        return []
    for commit in commits:
        login = run(["gh", "api", f"repos/{repo}/commits/{commit}", "--jq", ".author.login // empty"])
        if login != owner:
            print(f"Pending baseline: GitHub author for {commit} is {login or '<unassociated>'}, expected {owner}.", file=sys.stderr)
            return []
    return commits


def json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def prepare_metadata(actual: str, previous: str, commits: list[str]) -> dict[str, str]:
    policy_path = ROOT / "sources/policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    if guard.get("path") != CONFIG_PATH or guard.get("content_immutable_to_automation") is not True:
        raise ValueError("managed config protection invariant is invalid")
    owner = os.environ["GITHUB_REPOSITORY_OWNER"]
    now = datetime.now(timezone.utc).isoformat()
    guard["approved_git_blob_sha"] = actual
    guard["last_user_approved_baseline_update"] = {
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "reason": "User-authorized automatic baseline registration after GitHub verified every intervening uu.conf-changing commit is authored by the repository owner. Only metadata is updated; uu.conf bytes are immutable to automation.",
        "approval_mode": "owner_authored_config_history_with_user_authorization",
        "config_change_commits": commits,
        "actor": owner,
        "commit_sha": commits[-1],
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
    report = json.loads(report_path.read_text(encoding="utf-8"))
    config_bytes = (ROOT / CONFIG_PATH).read_bytes()
    report["baseline_sha256"] = hashlib.sha256(config_bytes).hexdigest()
    report["baseline_git_blob_sha"] = actual
    report["registered_baseline_git_blob_sha"] = actual
    report["baseline_matches_registered_blob"] = True
    report["owner_approved_change_pending_registration"] = False
    report["registration"] = {
        "status": "registered",
        "registered_at": now,
        "verified_owner_commits": commits,
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
        report = json.loads(report_path.read_text(encoding="utf-8"))
        expected_report = {
            "baseline_sha256": hashlib.sha256(original).hexdigest(),
            "baseline_git_blob_sha": actual,
            "registered_baseline_git_blob_sha": actual,
            "baseline_matches_registered_blob": True,
            "owner_approved_change_pending_registration": False,
        }
        changed_report = any(report.get(key) != value for key, value in expected_report.items())
        if changed_report and args.apply:
            report.update(expected_report)
            report_path.write_text(json_text(report), encoding="utf-8")
        print(json.dumps({"status": "audit_metadata_refreshed" if changed_report and args.apply else "no_change", "blob_sha": actual, "audit_report_refresh_needed": changed_report, "config_content_modified": False}, sort_keys=True))
        return 0

    commits = owner_approved_config_history(guard)
    if not commits:
        report_path = ROOT / "reports/config-drift-audit.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["baseline_sha256"] = hashlib.sha256(original).hexdigest()
        report["baseline_git_blob_sha"] = actual
        report["registered_baseline_git_blob_sha"] = previous
        report["baseline_matches_registered_blob"] = False
        report["owner_approved_change_pending_registration"] = True
        old_observation = report.get("observation", {})
        observed_at = old_observation.get("observed_at") if old_observation.get("observed_git_blob_sha") == actual else None
        report["observation"] = {
            "status": "observed_pending_owner_attribution",
            "observed_git_blob_sha": actual,
            "observed_sha256": hashlib.sha256(original).hexdigest(),
            "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
            "next_action": "Keep tracking and continue read-only audit; do not advance the approved baseline until all intervening config commits are verified owner-authored.",
        }
        if args.apply and report != json.loads(report_path.read_text(encoding="utf-8")):
            report_path.write_text(json_text(report), encoding="utf-8")
        print(json.dumps({"status": "observed_pending_owner_attribution", "observed_blob_sha": actual, "registered_blob_sha": previous, "config_content_modified": False}, sort_keys=True))
        return 0

    if not args.apply:
        print(json.dumps({"status": "verified_owner_change_ready", "previous_blob_sha": previous, "new_blob_sha": actual, "verified_commits": commits, "config_content_modified": False}, sort_keys=True))
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
        "verified_owner_commits": commits,
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
