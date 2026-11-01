#!/usr/bin/env python3
"""Fail-closed integrity verification of the user's authoritative config baseline."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    path = ROOT / guard["path"]
    data = path.read_bytes()
    actual = git_blob_sha(data)
    expected = guard["approved_git_blob_sha"]
    if actual != expected:
        raise ValueError(f"User config baseline mismatch for {guard['path']}: {actual}; expected {expected}")
    print(f"PASS: {guard['path']} is the registered user config baseline ({actual}).")
    print("The historical uploaded config is archival only and is not used as the authority for current checks.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
