#!/usr/bin/env python3
"""Register uu.conf changes only when the repository owner pushed them to the protected branch."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()


import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"
CONFIG = ROOT / "modules" / "uu.conf"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def owner_approved_push_changed_config() -> bool:
    if os.environ.get("GITHUB_EVENT_NAME") != "push":
        return False
    actor = os.environ.get("GITHUB_ACTOR", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    before = os.environ.get("GITHUB_BEFORE", "")
    after = os.environ.get("GITHUB_SHA", "")
    if not actor or actor != owner or not before or not after or set(before) == {"0"}:
        return False
    result = subprocess.run(
        ["git", "diff", "--name-only", before, after],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    return "modules/uu.conf" in result.stdout.splitlines()


def owner_approved_config_history(guard: dict) -> list[str]:
    """Recover interrupted registration only from owner-authored config commits."""
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event not in {"push", "workflow_dispatch"}:
        return []
    actor = os.environ.get("GITHUB_ACTOR", "")
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    ref = os.environ.get("GITHUB_REF", "")
    if event == "push" and (not actor or actor != owner):
        return []
    if event == "workflow_dispatch" and ref != "refs/heads/main":
        return []
    after = os.environ.get("GITHUB_SHA", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    baseline_commit = str(guard.get("last_user_approved_baseline_update", {}).get("commit_sha", ""))
    if (
        not owner or ref != "refs/heads/main"
        or not after or not repo or not baseline_commit
        or set(after) == {"0"} or set(baseline_commit) == {"0"}
    ):
        return []
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", baseline_commit, after],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    if ancestry.returncode != 0:
        return []
    history = subprocess.run(
        ["git", "log", "--format=%H", f"{baseline_commit}..{after}", "--", str(guard["path"])],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    commits = [line.strip() for line in history.stdout.splitlines() if line.strip()]
    if not commits:
        return []
    # Git author text can be forged. Require GitHub's account association for every commit.
    for commit_sha in commits:
        author = subprocess.run(
            ["gh", "api", f"repos/{repo}/commits/{commit_sha}", "--jq", ".author.login // empty"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        if author != owner:
            return []
    return commits


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    config_path = ROOT / guard["path"]
    actual = git_blob_sha(config_path.read_bytes())
    previous = str(guard["approved_git_blob_sha"])
    changed = actual != previous

    direct_push_approval = owner_approved_push_changed_config()
    recovered_commits = [] if direct_push_approval else owner_approved_config_history(guard)
    if not direct_push_approval and not recovered_commits:
        if changed:
            raise ValueError(
                "uu.conf differs from the approved baseline, but no current or recoverable owner-approved config change was verified; refusing automatic approval."
            )
        print(json.dumps({"registered": False, "reason": "no owner-approved uu.conf change", "blob_sha": actual}))
        return 0

    if not changed:
        print(json.dumps({"registered": False, "reason": "owner push did not change config content", "blob_sha": actual}))
        return 0

    guard["approved_git_blob_sha"] = actual
    approval_mode = "owner_push_changed_config" if direct_push_approval else "recovered_owner_authored_config_history"
    guard["last_user_approved_baseline_update"] = {
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "reason": (
            "Register the exact config version from an owner-authored push."
            if direct_push_approval else
            "Recover an interrupted registration after verifying every intervening uu.conf-changing commit is associated with the repository owner on GitHub. Automation does not edit uu.conf."
        ),
        "approval_mode": approval_mode,
        "config_change_commits": recovered_commits,
        "actor": os.environ.get("GITHUB_ACTOR"),
        "commit_sha": os.environ.get("GITHUB_SHA"),
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    POLICY.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "registered": True,
        "path": guard["path"],
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "actor": os.environ.get("GITHUB_ACTOR"),
        "approval_mode": approval_mode,
        "config_change_commits": recovered_commits,
        "config_file_modified": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
