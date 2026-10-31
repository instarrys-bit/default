#!/usr/bin/env python3
"""Fail-closed verification of the immutable uploaded Shadowrocket baseline."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sources" / "policy.json"

def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    baseline = policy["canonical_config"]
    path = ROOT / baseline["path"]
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    git_blob = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
    if sha256 != baseline["uploaded_sha256"]:
        raise ValueError(f"SHA-256 mismatch for {baseline['path']}: {sha256}")
    if git_blob != baseline["approved_git_blob_sha"]:
        raise ValueError(f"Git blob mismatch for {baseline['path']}: {git_blob}")
    if len(data) != int(baseline["uploaded_bytes"]):
        raise ValueError(f"Byte length mismatch for {baseline['path']}: {len(data)}")
    print(f"PASS: {baseline['path']} matches the immutable uploaded baseline.")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
