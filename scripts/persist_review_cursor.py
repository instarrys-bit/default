#!/usr/bin/env python3
"""Persist only a validated in-progress review cursor from a failed audit artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def persist_cursor(artifact: Path, destination: Path) -> str:
    if not artifact.is_file():
        print("No cursor artifact available; leaving any existing checkpoint unchanged.")
        return "missing"
    data = json.loads(artifact.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("unsupported review cursor schema")
    status = data.get("status")
    if status not in {"in_progress", "complete"}:
        raise ValueError("unsupported review cursor status")
    digest = data.get("snapshot_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("invalid cursor snapshot digest")
    candidate_count = data.get("candidate_count")
    next_index = data.get("next_index")
    batch_size = data.get("batch_size")
    if type(candidate_count) is not int or candidate_count < 0:
        raise ValueError("invalid cursor candidate count")
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("invalid cursor batch size")
    if type(next_index) is not int:
        raise ValueError("invalid cursor checkpoint index")
    if status == "complete":
        if next_index != candidate_count:
            raise ValueError("completed cursor must cover every candidate")
        destination.unlink(missing_ok=True)
        print("Review cursor is complete; removed stale persisted checkpoint if present.")
        return "complete"
    if not 1 <= next_index <= candidate_count:
        raise ValueError("invalid cursor checkpoint index")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Persisted in-progress review cursor at index {next_index}/{candidate_count}.")
    return "in_progress"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cursor-artifact", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    persist_cursor(args.cursor_artifact, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
