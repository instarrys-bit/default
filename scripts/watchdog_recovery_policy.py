#!/usr/bin/env python3
"""Bounded, deterministic retry policy for failed main-branch automation runs."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any


RETRYABLE_CONCLUSIONS = {"timed_out", "startup_failure"}


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def decide_recovery(
    runs: list[dict[str, Any]],
    *,
    source_run_id: str,
    source_sha: str,
    now: datetime | None = None,
    window: timedelta = timedelta(hours=24),
    max_retries: int = 2,
    base_cooldown: timedelta = timedelta(minutes=15),
) -> dict[str, Any]:
    """Decide whether a failed run may be retried, using prior same-SHA failures only."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if max_retries < 0 or base_cooldown.total_seconds() < 0:
        raise ValueError("retry limits and cooldown must be non-negative")

    prior = []
    for run in runs:
        if str(run.get("id", "")) == str(source_run_id):
            continue
        if run.get("head_branch") != "main" or run.get("head_sha") != source_sha:
            continue
        if run.get("status") != "completed" or run.get("conclusion") not in RETRYABLE_CONCLUSIONS:
            continue
        stamp = run.get("created_at")
        if not stamp:
            continue
        try:
            created = _timestamp(stamp)
        except (TypeError, ValueError):
            continue
        if now - window <= created <= now:
            prior.append((created, run))

    prior.sort(key=lambda item: item[0])
    attempts_used = len(prior)
    result = {
        "allowed": False,
        "source_run_id": str(source_run_id),
        "source_sha": source_sha,
        "prior_retryable_failures": attempts_used,
        "max_retries": max_retries,
        "retry_number": attempts_used + 1,
        "cooldown_seconds": 0,
        "reason": "",
    }

    if attempts_used >= max_retries:
        result["reason"] = "retry_limit_reached"
        return result

    if prior:
        cooldown_seconds = int(base_cooldown.total_seconds() * (2 ** (attempts_used - 1)))
        elapsed = (now - prior[-1][0]).total_seconds()
        result["cooldown_seconds"] = cooldown_seconds
        if elapsed < cooldown_seconds:
            result["reason"] = "cooldown_active"
            result["retry_after_seconds"] = max(0, int(cooldown_seconds - elapsed))
            return result

    result["allowed"] = True
    result["reason"] = "bounded_retry_allowed"
    result["retry_after_seconds"] = 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--base-cooldown-seconds", type=int, default=900)
    args = parser.parse_args()

    payload = json.load(sys.stdin)
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else payload
    if not isinstance(runs, list):
        raise SystemExit("workflow run input must be a list or contain workflow_runs")
    decision = decide_recovery(
        runs,
        source_run_id=args.source_run_id,
        source_sha=args.source_sha,
        max_retries=args.max_retries,
        base_cooldown=timedelta(seconds=args.base_cooldown_seconds),
    )
    print(json.dumps(decision, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
