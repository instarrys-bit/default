#!/usr/bin/env python3
"""Verify protected uu.conf content and reviewed-PR-only baseline metadata transitions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"
BASELINE_METADATA_PATHS = {
    "sources/policy.json",
    "automation/release_manifest.json",
    "automation/production_workflow_map.json",
    "automation/resource_write_sets.json",
}


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def load_json_at(ref: str, path: str) -> dict:
    return json.loads(run_git("show", f"{ref}:{path}"))


def validate_registration_metadata(
    base_guard: dict, head_guard: dict, actual_sha: str,
    commits: list[str],
) -> None:
    previous = base_guard.get("approved_git_blob_sha")
    new = head_guard.get("approved_git_blob_sha")
    update = head_guard.get("last_user_approved_baseline_update")
    if not isinstance(update, dict):
        raise ValueError("reviewed baseline PR metadata is missing")
    if update.get("previous_blob_sha") != previous or update.get("new_blob_sha") != new:
        raise ValueError("baseline registration previous/new SHA does not match the policy transition")
    if new != actual_sha:
        raise ValueError("registered baseline SHA does not match the current uu.conf Git blob")
    if update.get("approval_mode") != "reviewed_pull_request":
        raise ValueError("baseline metadata must use reviewed_pull_request approval mode")
    if not isinstance(update.get("actor"), str) or not update.get("actor"):
        raise ValueError("baseline registration actor evidence is missing")
    if update.get("config_change_commits") != commits or not commits:
        raise ValueError("baseline registration does not enumerate every intervening uu.conf commit")
    if update.get("commit_sha") != commits[0]:
        raise ValueError("baseline registration anchor must be the newest observed uu.conf commit")
    try:
        datetime.fromisoformat(str(update.get("registered_at", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("baseline registration timestamp must be ISO-8601") from exc


def verify_human_approval(repository: str, pr_number: str) -> None:
    result = subprocess.run(
        [
            "gh", "api", f"repos/{repository}/pulls/{pr_number}/reviews",
            "--jq", '[.[] | select(.state == "APPROVED" and .user.type != "Bot")] | length',
        ],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    try:
        approvals = int(result.stdout.strip() or "0")
    except ValueError as exc:
        raise ValueError("could not parse human PR approval count") from exc
    if approvals < 1:
        raise ValueError("baseline metadata PR requires at least one human APPROVED review")


def verify_registration(base: str, head: str) -> None:
    # Metadata registration PRs must never change the protected config bytes.
    run_git("diff", "--quiet", base, head, "--", "modules/uu.conf")

    base_policy = load_json_at(base, "sources/policy.json")
    head_policy = json.loads(POLICY.read_text(encoding="utf-8"))
    base_guard = base_policy.get("managed_config_guard")
    head_guard = head_policy.get("managed_config_guard")
    if not isinstance(base_guard, dict) or not isinstance(head_guard, dict):
        raise ValueError("managed_config_guard must remain an object")
    if base_guard.get("path") != "modules/uu.conf" or head_guard.get("path") != "modules/uu.conf":
        raise ValueError("managed config identity must remain modules/uu.conf")

    changed = (
        base_guard.get("approved_git_blob_sha") != head_guard.get("approved_git_blob_sha")
        or base_guard.get("last_user_approved_baseline_update")
        != head_guard.get("last_user_approved_baseline_update")
    )
    if not changed:
        print("PASS: no approved uu.conf baseline metadata transition in this PR.")
        return

    changed_paths = set(run_git("diff", "--name-only", base, head).splitlines())
    unexpected = changed_paths - BASELINE_METADATA_PATHS
    if unexpected:
        raise ValueError(
            "baseline metadata must be updated in a separate PR containing only the four approved metadata paths; "
            f"unexpected paths: {sorted(unexpected)}"
        )
    changed_guard_fields = {
        key for key in set(base_guard) | set(head_guard)
        if base_guard.get(key) != head_guard.get(key)
    }
    if changed_guard_fields - {"approved_git_blob_sha", "last_user_approved_baseline_update"}:
        raise ValueError("baseline metadata PR may change only the approved SHA and its registration record")

    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        raise ValueError("baseline metadata changes must be validated in a pull_request workflow")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    pr_number = os.environ.get("PR_NUMBER", "")
    if not repository or not pr_number:
        raise ValueError("baseline metadata PR identity is missing")
    verify_human_approval(repository, pr_number)

    actual_sha = run_git("hash-object", "modules/uu.conf")
    anchor = str(base_guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if len(anchor) != 40:
        raise ValueError("previous registered baseline commit anchor is invalid")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", anchor, base],
        cwd=ROOT, check=True, capture_output=True,
    )
    commits_text = run_git("log", "--format=%H", f"{anchor}..{base}", "--", "modules/uu.conf")
    commits = [line for line in commits_text.splitlines() if line]
    if not commits:
        raise ValueError("no intervening uu.conf commits were found; refusing baseline re-registration")
    validate_registration_metadata(base_guard, head_guard, actual_sha, commits)

    metadata_policy = head_guard.get("baseline_metadata_policy", {})
    for key in (
        "automation_may_update_registered_blob_sha",
        "automation_may_update_release_baseline_sha",
        "automation_may_update_approved_baseline_sha",
    ):
        if metadata_policy.get(key) is not True:
            raise ValueError(f"baseline metadata policy must authorize the explicit metadata-only writer: {key}")
    if metadata_policy.get("reviewed_pr_required") is not True or metadata_policy.get("owner_authored_config_history_required") is not True:
        raise ValueError("manual metadata PRs must remain reviewed and automatic registration must verify owner-authored history")

    release = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))
    pin = release.get("implementation_pins", {}).get("config_baseline", {})
    if pin.get("path") != "modules/uu.conf" or pin.get("access") != "read_only" or pin.get("git_blob_sha") != actual_sha:
        raise ValueError("release manifest does not pin the verified read-only uu.conf blob")
    sync = release.get("execution_policy", {}).get("watchdog_baseline_metadata_sync", {})
    if (sync.get("writer") != "Storage Management / File Management"
            or sync.get("trigger") != ["push", "schedule"]
            or set(sync.get("write_allowlist", [])) != BASELINE_METADATA_PATHS):
        raise ValueError("release manifest metadata-only writer contract is inconsistent")
    release_sha = run_git("hash-object", "automation/release_manifest.json")
    workflow_map = json.loads((ROOT / "automation/production_workflow_map.json").read_text(encoding="utf-8"))
    write_sets = json.loads((ROOT / "automation/resource_write_sets.json").read_text(encoding="utf-8"))
    if workflow_map.get("review_context", {}).get("release_manifest_blob_sha") != release_sha:
        raise ValueError("workflow map release-manifest pin is stale")
    if write_sets.get("review_context", {}).get("release_manifest_blob_sha") != release_sha:
        raise ValueError("resource write inventory release-manifest pin is stale")
    print(
        f"PASS: reviewed baseline PR records {len(commits)} uu.conf commits; "
        f"baseline {actual_sha}; config content unchanged in this PR."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-owner-push-change", action="store_true",
                        help="Deprecated compatibility flag; author attribution never grants metadata write permission.")
    parser.add_argument("--baseline-only", action="store_true",
                        help="Verify the managed config baseline without changing it.")
    parser.add_argument("--verify-registration", action="store_true",
                        help="Verify a separate human-reviewed metadata-only baseline PR.")
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args()
    if args.verify_registration:
        if not args.base or not args.head:
            parser.error("--verify-registration requires --base and --head")
        verify_registration(args.base, args.head)
        return 0

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    path = ROOT / guard["path"]
    actual = git_blob_sha(path.read_bytes())
    expected = guard["approved_git_blob_sha"]
    if actual != expected:
        print(
            f"OBSERVED CONFIG CHANGE: {guard['path']} current_blob_sha={actual} "
            f"registered_baseline_sha={expected}. Emit a runner-local proposal and continue read-only audit; "
            "baseline metadata registration requires owner-attributed commit history; unverified attribution remains pending."
        )
        return 0
    print(f"PASS: {guard['path']} matches the registered baseline ({actual}); read-only audit may proceed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
