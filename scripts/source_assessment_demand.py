#!/usr/bin/env python3
"""Decide whether Watchdog must continue the bounded monolithic source assessment."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse


ACTIVE = {"QUEUED", "CLAIMED", "VERIFYING"}
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "DEAD_LETTER"}


def assessment_backlog_demand(manifest: dict, queue: dict) -> dict:
    if not isinstance(manifest, dict) or not isinstance(queue, dict):
        raise ValueError("manifest and queue must be JSON objects")
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("source candidate manifest metadata is missing")
    pending = metadata.get("pending_assessment_count")
    if isinstance(pending, bool) or not isinstance(pending, int) or pending < 0:
        raise ValueError("pending_assessment_count must be a non-negative integer")
    if pending == 0:
        return {"action": "clear", "pending_assessment_count": 0}
    latest = metadata.get("latest_assessment")
    if not isinstance(latest, dict):
        return {"action": "blocked", "reason": "assessment cursor metadata is missing",
                "pending_assessment_count": pending}
    cursor = latest.get("next_cursor_url")
    parsed = urlparse(cursor) if isinstance(cursor, str) else None
    if (parsed is None or parsed.scheme != "https"
            or parsed.hostname != "raw.githubusercontent.com"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or len([part for part in parsed.path.split("/") if part]) < 4):
        return {"action": "blocked", "reason": "assessment cursor is missing or outside the approved raw GitHub origin",
                "pending_assessment_count": pending}
    discovery_fingerprint = metadata.get("discovery_fingerprint")
    if not isinstance(discovery_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", discovery_fingerprint):
        return {"action": "blocked", "reason": "discovery fingerprint is not a SHA-256 digest",
                "pending_assessment_count": pending}
    cursor_sha256 = hashlib.sha256(cursor.encode("utf-8")).hexdigest()
    key = f"source-assessment:cursor:{cursor_sha256}:{discovery_fingerprint}"
    tasks = queue.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("task queue tasks must be an array")
    matching = [task for task in tasks if isinstance(task, dict) and task.get("idempotency_key") == key]
    for task in matching:
        status = task.get("status")
        if status in ACTIVE:
            return {"action": "already_queued" if status == "QUEUED" else "in_progress",
                    "idempotency_key": key, "cursor_sha256": cursor_sha256,
                    "discovery_fingerprint": discovery_fingerprint,
                    "pending_assessment_count": pending}
        if status in TERMINAL:
            return {"action": "stalled", "reason": "the same cursor batch already reached a terminal task state; refusing an infinite no-progress replay",
                    "task_id": task.get("task_id"), "task_status": status,
                    "idempotency_key": key, "cursor_sha256": cursor_sha256,
                    "discovery_fingerprint": discovery_fingerprint,
                    "pending_assessment_count": pending}
    return {"action": "enqueue", "idempotency_key": key,
            "cursor_sha256": cursor_sha256,
            "discovery_fingerprint": discovery_fingerprint,
            "pending_assessment_count": pending,
            "reason": "verified source assessment backlog remains after production inputs were already satisfied"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        queue = json.loads(args.queue.read_text(encoding="utf-8"))
        print(json.dumps(assessment_backlog_demand(manifest, queue), sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # Return a valid blocked decision to the workflow so it can emit the
        # intended fail-closed diagnostic instead of aborting command substitution.
        print(json.dumps({"action": "blocked", "reason": str(exc)}, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
