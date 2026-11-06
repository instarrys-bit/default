#!/usr/bin/env python3
"""Restore inventory files from automation/.restore/*.b64 chunks and verify hashes."""
from __future__ import annotations
import base64, hashlib, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "automation" / ".restore" / "meta.json"

def restore(prefix: str, dest: str, n: int, expected_sha: str, expected_len: int) -> None:
    parts = [(ROOT / "automation" / ".restore" / f"{prefix}.{i:02d}.b64").read_text(encoding="ascii").strip() for i in range(n)]
    raw = base64.b64decode("".join(parts))
    if len(raw) != expected_len:
        raise SystemExit(f"{prefix}: bad length {len(raw)} != {expected_len}")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha:
        raise SystemExit(f"{prefix}: bad sha256 {digest}")
    path = ROOT / dest
    path.write_bytes(raw)
    print(f"restored {dest} ({len(raw)} bytes)")

def main() -> int:
    meta = json.loads(META.read_text(encoding="utf-8"))
    restore("wm", meta["wm"]["dest"], meta["wm"]["chunks"], meta["wm"]["sha256"], meta["wm"]["bytes"])
    restore("ws", meta["ws"]["dest"], meta["ws"]["chunks"], meta["ws"]["sha256"], meta["ws"]["bytes"])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
