#!/usr/bin/env python3
"""Select stale main-branch production audit runs for bounded Watchdog recovery."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any


def stale_candidates(
    payload: dict[str, Any],
    current_main: str,
    now: datetime | None = None,
    timeout_seconds: int = 21600,
) -> list[tuple[str, str, str]]:
    now = now or datetime.now(timezone.utc)
    candidates: list[tuple[str, str, str]] = []
    for run in payload.get("workflow_runs", []):
        if not isinstance(run, dict) or run.get("status") == "completed":
            continue
        if run.get("head_branch") != "main":
            continue
        run_id = run.get("id")
        if not run_id:
            continue
        run_sha = run.get("head_sha") or ""
        if run_sha != current_main:
            candidates.append((str(run_id), "superseded", str(run_sha)))
            continue
        stamp = run.get("run_started_at") or run.get("created_at")
        if not stamp:
            continue
        started = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if (now - started).total_seconds() > timeout_seconds:
            candidates.append((str(run_id), "timeout", str(run_sha)))
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-main", required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("workflow run payload must be a JSON object")
        for run_id, reason, run_sha in stale_candidates(payload, args.current_main):
            print(run_id, reason, run_sha)
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        print(f"Invalid workflow run payload: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
