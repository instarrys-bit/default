#!/usr/bin/env python3
"""Append a report to GITHUB_STEP_SUMMARY without exceeding GitHub's size limit."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

DEFAULT_MAX_BYTES = 850_000
TRUNCATION_MARKER = (
    "\n\n> [Summary truncated] The complete report is retained in the workflow "
    "workspace/artifacts; this display was capped to protect GitHub's 1 MiB step-summary limit.\n"
)


def append_summary(source: Path, summary: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    if max_bytes <= len(TRUNCATION_MARKER.encode("utf-8")):
        raise ValueError("max_bytes must leave room for the truncation marker")
    source_bytes = source.read_bytes()
    existing = summary.read_bytes() if summary.exists() else b""
    remaining = max_bytes - len(existing)
    if remaining <= 0:
        return {"appended_bytes": 0, "truncated": bool(source_bytes), "total_bytes": len(existing)}
    if len(source_bytes) <= remaining:
        payload = source_bytes
        truncated = False
    else:
        marker = TRUNCATION_MARKER.encode("utf-8")
        content_budget = max(0, remaining - len(marker))
        payload = source_bytes[:content_budget].decode("utf-8", errors="ignore").encode("utf-8") + marker[:remaining - content_budget]
        truncated = True
    summary.parent.mkdir(parents=True, exist_ok=True)
    with summary.open("ab") as stream:
        stream.write(payload)
    return {
        "appended_bytes": len(payload),
        "truncated": truncated,
        "total_bytes": len(existing) + len(payload),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        raise SystemExit("GITHUB_STEP_SUMMARY is not set")
    result = append_summary(Path(args.input), Path(summary_path), args.max_bytes)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
