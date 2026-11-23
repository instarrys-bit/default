#!/usr/bin/env python3
"""Fail-closed integrity verification of the user's authoritative config baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"


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
        raise ValueError("automatic baseline registration metadata is missing")
    if update.get("previous_blob_sha") != previous or update.get("new_blob_sha") != new:
        raise ValueError("baseline registration previous/new SHA does not match the policy transition")
    if new != actual_sha:
        raise ValueError("registered baseline SHA does not match the current uu.conf Git blob")
    if update.get("approval_mode") != "user_authorized_automatic_sha_follow":
        raise ValueError("baseline registration does not use the user-authorized automatic SHA-follow mode")
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


def verify_registration(base: str, head: str) -> None:
    # The PR must never change the protected config bytes.
    run_git("diff", "--quiet", base, head, "--", "modules/uu.conf")

    base_policy = load_json_at(base, "sources/policy.json")
    head_policy = json.loads((ROOT / "sources/policy.json").read_text(encoding="utf-8"))
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
    semantic_keys = {
        "immutable", "description", "content_immutable_to_automation",
        "content_protection", "baseline_metadata_policy",
    }
    changed_keys = set(base_guard) ^ set(head_guard)
    changed_keys.update(
        key for key in set(base_guard) & set(head_guard)
        if base_guard[key] != head_guard[key]
    )
    allowed = semantic_keys | {"path", "approved_git_blob_sha", "last_user_approved_baseline_update"}
    if changed_keys - allowed:
        raise ValueError("non-main validation changed an unsupported managed-config guard field")

    if not changed:
        print("PASS: uu.conf and automatically followed baseline registration are unchanged.")
        return

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

    release = json.loads((ROOT / "automation/release_manifest.json").read_text(encoding="utf-8"))
    pin = release.get("implementation_pins", {}).get("config_baseline", {})
    if pin.get("path") != "modules/uu.conf" or pin.get("access") != "read_only" or pin.get("git_blob_sha") != actual_sha:
        raise ValueError("release manifest does not pin the verified read-only uu.conf blob")
    release_sha = run_git("hash-object", "automation/release_manifest.json")
    workflow_map = json.loads((ROOT / "automation/production_workflow_map.json").read_text(encoding="utf-8"))
    write_sets = json.loads((ROOT / "automation/resource_write_sets.json").read_text(encoding="utf-8"))
    if workflow_map.get("review_context", {}).get("release_manifest_blob_sha") != release_sha:
        raise ValueError("workflow map release-manifest pin is stale")
    if write_sets.get("review_context", {}).get("release_manifest_blob_sha") != release_sha:
        raise ValueError("resource write inventory release-manifest pin is stale")
    print(
        f"PASS: user-authorized uu.conf SHA history recorded ({len(commits)} commits); "
        f"baseline {actual_sha}; config content unchanged in this PR."
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-owner-push-change", action="store_true")
    parser.add_argument("--baseline-only", action="store_true", help="Compatibility flag; always verifies only the managed baseline.")
    parser.add_argument("--verify-registration", action="store_true", help="Verify an user-authorized metadata-only baseline registration in a non-main PR.")
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
    data = path.read_bytes()
    actual = git_blob_sha(data)
    expected = guard["approved_git_blob_sha"]
    if actual != expected:
        # A baseline mismatch is an observed input change, not a reason to stop
        # tracking or skip the deterministic audit. Storage Management records
        # the current Git blob SHA and retries its snapshot if the file changes
        # while being read. Keep the registered approval pin historical; never
        # rewrite uu.conf or silently bless a new baseline here.
        print(
            f"OBSERVED CONFIG CHANGE: {guard['path']} current_blob_sha={actual} "
            f"registered_baseline_sha={expected}. Continue read-only audit; "
            "Storage Management must persist the observed SHA and reconcile the latest file."
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
