#!/usr/bin/env python3
"""Capture persistent repository mutations made by shell and Git child processes.

The Python audit hook records Python-level filesystem events. This companion
snapshot records the final repository tree delta against the job's checkout,
including files changed or committed by shell/Git subprocesses. It stores paths
and run metadata only, never file contents or credentials.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE_ENV = "AUTOMATION_WRITE_TRACE_PATH"


def git_output(args: list[str], root: Path = ROOT) -> bytes:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=False,
        stdin=subprocess.DEVNULL, timeout=30, check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace")[-1000:]
        raise RuntimeError("git write-trace inspection failed: " + message)
    return completed.stdout


def collect_changed_paths(baseline_sha: str, root: Path = ROOT, runner=git_output) -> list[str]:
    if not isinstance(baseline_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", baseline_sha):
        raise ValueError("baseline SHA must be a full lowercase Git commit SHA")
    found: set[str] = set()
    commands = (
        ["diff", "--name-only", "-z", baseline_sha, "HEAD"],
        ["diff", "--name-only", "-z"],
        ["diff", "--cached", "--name-only", "-z"],
        ["ls-files", "--others", "--exclude-standard", "-z"],
    )
    for command in commands:
        raw = runner(command, root)
        for encoded in raw.split(b"\0"):
            if not encoded:
                continue
            path = encoded.decode("utf-8", errors="surrogateescape")
            candidate = Path(path)
            if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
                raise ValueError("git write trace returned an unsafe repository path")
            found.add(candidate.as_posix())
    return sorted(found)


def append_trace(paths: list[str], baseline_sha: str, trace_path: Path) -> dict:
    head_sha = git_output(["rev-parse", "HEAD"]).decode("ascii", errors="strict").strip()
    workflow = os.environ.get("GITHUB_WORKFLOW", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    task_id = os.environ.get("AUTOMATION_TASK_ID", "")
    lease_required = os.environ.get("AUTOMATION_REQUIRE_RESOURCE_LEASE") == "1"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    with trace_path.open("a", encoding="utf-8") as stream:
        for path in paths:
            stream.write(json.dumps({
                "operation": "shell_git_persistent_repository_change",
                "path": path,
                "workflow": workflow,
                "run_id": run_id,
                "task_id": task_id,
                "lease_required": lease_required,
                "baseline_sha": baseline_sha,
                "head_sha": head_sha,
            }, sort_keys=True) + "\n")
        stream.write(json.dumps({
            "operation": "shell_git_repository_scan_complete",
            "changed_path_count": len(paths),
            "workflow": workflow,
            "run_id": run_id,
            "task_id": task_id,
            "lease_required": lease_required,
            "baseline_sha": baseline_sha,
            "head_sha": head_sha,
        }, sort_keys=True) + "\\n")
    return {"changed_path_count": len(paths), "baseline_sha": baseline_sha, "head_sha": head_sha}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-sha", required=True)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args(argv)
    trace_value = args.trace or os.environ.get(TRACE_ENV)
    if not trace_value:
        raise SystemExit("write trace path is required")
    trace = Path(trace_value)
    try:
        paths = collect_changed_paths(args.baseline_sha)
        result = append_trace(paths, args.baseline_sha, trace)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print("WRITE TRACE CAPTURE ERROR: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
