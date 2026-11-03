#!/usr/bin/env python3
"""Persist unknown repository paths in the Watchdog registration inbox.

Registration is deliberately not approval: every new path remains pending
classification and continues to block production until explicitly classified.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def normalize_path(value: str) -> str:
    path = value.strip().removeprefix("./")
    if (not path or path.startswith("/") or "\\" in path
            or any(part in {"", ".", ".."} for part in path.split("/"))
            or any(ord(char) < 32 for char in path)):
        raise ValueError(f"unsafe or invalid repository path: {value!r}")
    return path


def register_paths(paths: list[str], ledger: dict, *, event: str, revision: str,
                   run_id: str, run_url: str, now: str | None = None) -> dict:
    if ledger.get("schema_version") != 1 or not isinstance(ledger.get("entries"), list):
        raise ValueError("unsupported Watchdog registration ledger")
    stamp = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entries = {item["path"]: item for item in ledger["entries"]}
    for raw in sorted(set(paths)):
        path = normalize_path(raw)
        item = entries.get(path)
        if item is None:
            item = {
                "path": path,
                "status": "PENDING_CLASSIFICATION",
                "first_seen_at": stamp,
                "last_seen_at": stamp,
                "seen_count": 0,
            }
            entries[path] = item
        item["last_seen_at"] = stamp
        item["seen_count"] += 1
        item["last_seen_event"] = event
        item["last_seen_revision"] = revision
        item["last_seen_run_id"] = str(run_id)
        item["last_seen_run_url"] = run_url
        # Never silently reopen a previously classified path; its classification
        # remains explicit, while the new observation is still recorded.
    ledger["entries"] = sorted(entries.values(), key=lambda item: item["path"])
    ledger["updated_at"] = stamp
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths-json", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    paths = json.loads(args.paths_json)
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError("paths-json must be a JSON string array")
    if args.ledger.exists():
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    else:
        ledger = {"schema_version": 1, "purpose": "Watchdog inbox for unregistered repository paths; registration is not approval.", "entries": []}
    updated = register_paths(paths, ledger, event=args.event, revision=args.revision,
                             run_id=args.run_id, run_url=args.run_url)
    args.ledger.parent.mkdir(parents=True, exist_ok=True)
    args.ledger.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"registered_count": len(paths), "pending_count": sum(
        item.get("status") == "PENDING_CLASSIFICATION" for item in updated["entries"]
    ), "paths": sorted(set(normalize_path(path) for path in paths))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
