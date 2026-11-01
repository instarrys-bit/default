#!/usr/bin/env python3
"""Register ss.conf changes only when the repository owner pushed them to the protected branch."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"
CONFIG = ROOT / "shadowrocket" / "ss.conf"


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
    return "shadowrocket/ss.conf" in result.stdout.splitlines()


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    config_path = ROOT / guard["path"]
    actual = git_blob_sha(config_path.read_bytes())
    previous = str(guard["approved_git_blob_sha"])
    changed = actual != previous

    if not owner_approved_push_changed_config():
        if changed:
            raise ValueError(
                "ss.conf differs from the approved baseline, but this run is not an owner-authored push changing ss.conf; refusing automatic approval."
            )
        print(json.dumps({"registered": False, "reason": "no owner-approved ss.conf change", "blob_sha": actual}))
        return 0

    if not changed:
        print(json.dumps({"registered": False, "reason": "owner push did not change config content", "blob_sha": actual}))
        return 0

    guard["approved_git_blob_sha"] = actual
    guard["last_user_approved_baseline_update"] = {
        "previous_blob_sha": previous,
        "new_blob_sha": actual,
        "reason": "Repository owner pushed an ss.conf change; register that exact user-approved file version. Automation does not edit ss.conf.",
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
        "config_file_modified": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
