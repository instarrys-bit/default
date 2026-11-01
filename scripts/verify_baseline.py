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

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-owner-push-change", action="store_true")
    parser.add_argument("--baseline-only", action="store_true", help="Compatibility flag; always verifies only the managed baseline.")
    args = parser.parse_args()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    path = ROOT / guard["path"]
    data = path.read_bytes()
    actual = git_blob_sha(data)
    expected = guard["approved_git_blob_sha"]
    if actual != expected:
        if args.allow_owner_push_change and owner_approved_push_changed_config():
            print(
                f"PASS: {guard['path']} changed in a repository-owner push; structural validation may proceed. "
                "The publishing workflow will register this exact blob SHA before modifying derived rule sets."
            )
            return 0
        raise ValueError(f"User config baseline mismatch for {guard['path']}: {actual}; expected {expected}")
    print(f"PASS: {guard['path']} is the registered user config baseline ({actual}).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
