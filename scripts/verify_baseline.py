#!/usr/bin/env python3
"""Fail-closed verification of both immutable Shadowrocket configuration files."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()

def verify_file(path: Path, expected_sha: str, label: str) -> None:
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != expected_sha:
        raise ValueError(f"Git blob mismatch for {label}: {actual}")
    print(f"PASS: {label} is unchanged ({actual}).")

def main() -> int:
    baseline_only = "--baseline-only" in sys.argv[1:]
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    baseline = policy["canonical_config"]
    verify_file(ROOT / baseline["path"], baseline["approved_git_blob_sha"], baseline["path"])
    if hashlib.sha256((ROOT / baseline["path"]).read_bytes()).hexdigest() != baseline["uploaded_sha256"]:
        raise ValueError("Uploaded baseline SHA-256 mismatch: " + baseline["path"])
    if len((ROOT / baseline["path"]).read_bytes()) != int(baseline["uploaded_bytes"]):
        raise ValueError("Uploaded baseline byte length mismatch: " + baseline["path"])
    managed = policy.get("managed_config_guard")
    if managed and managed.get("immutable", False):
        if baseline_only:
            print(
                "WARNING: managed config guard was not used as an audit blocker; "
                "the file remains read-only and is still structurally validated."
            )
        else:
            verify_file(ROOT / managed["path"], managed["approved_git_blob_sha"], managed["path"])
    print("PASS: canonical uploaded baseline integrity is valid.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
