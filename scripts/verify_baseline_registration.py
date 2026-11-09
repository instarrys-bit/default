#!/usr/bin/env python3
"""Verify a proposed owner-approved uu.conf baseline registration without editing the config."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = "modules/uu.conf"
POLICY_PATH = "sources/policy.json"
RELEASE_PATH = "automation/release_manifest.json"
WORKFLOW_MAP_PATH = "automation/production_workflow_map.json"
WRITE_SETS_PATH = "automation/resource_write_sets.json"
SEMANTIC_GUARD_KEYS = {
    "immutable", "description", "content_immutable_to_automation",
    "content_protection", "baseline_metadata_policy",
}


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def load_json_at(ref: str, path: str) -> dict:
    return json.loads(run_git("show", f"{ref}:{path}"))


def validate_registration_metadata(
    base_guard: dict, head_guard: dict, actual_sha: str,
    commits: list[str], owner: str,
) -> None:
    previous = base_guard.get("approved_git_blob_sha")
    new = head_guard.get("approved_git_blob_sha")
    update = head_guard.get("last_user_approved_baseline_update")
    if not isinstance(update, dict):
        raise ValueError("owner baseline registration metadata is missing")
    if update.get("previous_blob_sha") != previous or update.get("new_blob_sha") != new:
        raise ValueError("baseline registration previous/new SHA does not match the policy transition")
    if new != actual_sha:
        raise ValueError("registered baseline SHA does not match the current uu.conf Git blob")
    if update.get("approval_mode") != "recovered_owner_authored_config_history":
        raise ValueError("baseline registration must use the owner-history recovery approval mode")
    if update.get("actor") != owner:
        raise ValueError("baseline registration actor is not the repository owner")
    if update.get("config_change_commits") != commits or not commits:
        raise ValueError("baseline registration does not enumerate every intervening uu.conf commit")
    if update.get("commit_sha") != commits[0]:
        raise ValueError("baseline registration anchor must be the newest verified uu.conf commit")
    try:
        datetime.fromisoformat(str(update.get("registered_at", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("baseline registration timestamp must be ISO-8601") from exc


def verify(base: str, head: str) -> None:
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not owner or not repository or "/" not in repository:
        raise ValueError("GitHub repository owner/context is unavailable")
    if run_git("diff", "--quiet", base, head, "--", CONFIG_PATH) != "":
        raise ValueError("non-main validation may not change modules/uu.conf")

    base_policy = load_json_at(base, POLICY_PATH)
    head_policy = json.loads((ROOT / POLICY_PATH).read_text(encoding="utf-8"))
    base_guard = base_policy.get("managed_config_guard")
    head_guard = head_policy.get("managed_config_guard")
    if not isinstance(base_guard, dict) or not isinstance(head_guard, dict):
        raise ValueError("managed_config_guard must remain an object")
    if base_guard.get("path") != CONFIG_PATH or head_guard.get("path") != CONFIG_PATH:
        raise ValueError("managed config identity must remain modules/uu.conf")

    changed = (
        base_guard.get("approved_git_blob_sha") != head_guard.get("approved_git_blob_sha")
        or base_guard.get("last_user_approved_baseline_update")
        != head_guard.get("last_user_approved_baseline_update")
    )
    changed_keys = set(base_guard) ^ set(head_guard)
    changed_keys.update(
        key for key in set(base_guard) & set(head_guard)
        if base_guard[key] != head_guard[key]
    )
    if changed_keys - (SEMANTIC_GUARD_KEYS | {"path", "approved_git_blob_sha", "last_user_approved_baseline_update"}):
        raise ValueError("non-main validation changed an unsupported managed-config guard field")

    if not changed:
        if (
            base_guard.get("approved_git_blob_sha") != head_guard.get("approved_git_blob_sha")
            or base_guard.get("last_user_approved_baseline_update")
            != head_guard.get("last_user_approved_baseline_update")
        ):
            raise ValueError("owner baseline identity or registration changed unexpectedly")
        print("PASS: uu.conf and owner-approved baseline registration are unchanged.")
        return

    if run_git("diff", "--quiet", base, head, "--", CONFIG_PATH) != "":
        raise ValueError("baseline registration PR also changes protected config content")
    actual_sha = run_git("hash-object", CONFIG_PATH)
    anchor = str(base_guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if len(anchor) != 40:
        raise ValueError("previous owner-approved baseline commit anchor is invalid")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", anchor, base],
        cwd=ROOT, check=True, capture_output=True,
    )
    commits_text = run_git("log", "--format=%H", f"{anchor}..{base}", "--", CONFIG_PATH)
    commits = [line for line in commits_text.splitlines() if line]
    if not commits:
        raise ValueError("no intervening uu.conf commits were found; refusing baseline re-registration")
    validate_registration_metadata(base_guard, head_guard, actual_sha, commits, owner)

    for commit in commits:
        result = subprocess.run(
            ["gh", "api", f"repos/{repository}/commits/{commit}", "--jq", ".author.login // empty"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        if result.stdout.strip() != owner:
            raise ValueError(f"uu.conf commit {commit} is not associated with repository owner {owner}")

    release = json.loads((ROOT / RELEASE_PATH).read_text(encoding="utf-8"))
    pin = release.get("implementation_pins", {}).get("config_baseline", {})
    if pin.get("path") != CONFIG_PATH or pin.get("access") != "read_only" or pin.get("git_blob_sha") != actual_sha:
        raise ValueError("release manifest does not pin the verified read-only uu.conf blob")
    release_sha = run_git("hash-object", RELEASE_PATH)
    workflow_map = json.loads((ROOT / WORKFLOW_MAP_PATH).read_text(encoding="utf-8"))
    write_sets = json.loads((ROOT / WRITE_SETS_PATH).read_text(encoding="utf-8"))
    if workflow_map.get("review_context", {}).get("release_manifest_blob_sha") != release_sha:
        raise ValueError("workflow map release-manifest pin is stale")
    if write_sets.get("review_context", {}).get("release_manifest_blob_sha") != release_sha:
        raise ValueError("resource write inventory release-manifest pin is stale")
    print(
        f"PASS: owner-authored uu.conf history verified ({len(commits)} commits); "
        f"baseline {actual_sha}; config content unchanged in this PR."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    verify(args.base, args.head)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
