#!/usr/bin/env python3
"""Fail-closed filesystem write guard for all repository-local mutations in authorized production runs."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_OPEN = open
_TRACE_ACTIVE = False
PROTECTED_PATHS = {"modules/uu.conf"}
# Every repository-relative mutation is lease-gated during an authorized
# production task. Per-run temporary files outside the checkout remain exempt.
_INSTALLED = False

def _requires_resource_lease(relative: str | None) -> bool:
    return bool(relative)



def _repo_relative(path) -> str | None:
    try:
        candidate = Path(os.fsdecode(path))
    except (TypeError, ValueError):
        return None
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise PermissionError("repository write path cannot be resolved safely") from exc
    try:
        resolved_relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        # A path lexically inside the repository must not escape through a symlink.
        try:
            candidate.relative_to(ROOT.resolve())
        except ValueError:
            return None
        raise PermissionError("repository write path escapes through a symlink")
    lexical_value = None
    try:
        lexical_value = candidate.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        # External symlinks/hardlinks resolving into the repository are still protected.
        pass
    resolved_value = resolved_relative.as_posix()
    if lexical_value in PROTECTED_PATHS or resolved_value in PROTECTED_PATHS:
        raise PermissionError("owner-managed protected file is read-only")
    return resolved_value if resolved_value not in {"", "."} else None


def _record_write_trace(path, operation: str) -> None:
    """Append path-only runtime evidence outside the repository; never record file contents or secrets."""
    global _TRACE_ACTIVE
    trace_path = os.environ.get("AUTOMATION_WRITE_TRACE_PATH")
    if not trace_path or _TRACE_ACTIVE:
        return
    relative = _repo_relative(path)
    if not _requires_resource_lease(relative):
        return
    record = {
        "operation": operation,
        "path": relative,
        "workflow": os.environ.get("GITHUB_WORKFLOW", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "task_id": os.environ.get("AUTOMATION_TASK_ID") or os.environ.get("AUTOMATION_TASK_ID_BASE", ""),
        "lease_required": os.environ.get("AUTOMATION_REQUIRE_RESOURCE_LEASE") == "1",
    }
    _TRACE_ACTIVE = True
    try:
        destination = Path(trace_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with _ORIGINAL_OPEN(destination, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    finally:
        _TRACE_ACTIVE = False


def authorize_write_path(path) -> None:
    """Reject owner-managed protected files and fence production modules, scripts, and rulesets."""
    relative = _repo_relative(path)
    if relative is None:
        # A pre-existing external hard link to the protected config has a different
        # pathname but the same inode; deny it as well.
        try:
            candidate_stat = Path(os.fsdecode(path)).stat()
            protected_stats = [
                (ROOT / item).stat()
                for item in PROTECTED_PATHS
                if (ROOT / item).exists()
            ]
            if any(
                (candidate_stat.st_dev, candidate_stat.st_ino) == (item.st_dev, item.st_ino)
                for item in protected_stats
            ):
                raise PermissionError("owner-managed protected file is read-only")
        except FileNotFoundError:
            pass
        return
    if relative in PROTECTED_PATHS:
        raise PermissionError(f"owner-managed protected file is read-only: {relative}")
    if (
        os.environ.get("AUTOMATION_REQUIRE_RESOURCE_LEASE") != "1"
        or not _requires_resource_lease(relative)
    ):
        return
    from resource_lease_runtime import assert_resource_lease_from_environment
    assert_resource_lease_from_environment(relative)


def _audit_hook(event: str, args: tuple) -> None:
    # Capability children must not escape Python-level filesystem fencing by
    # launching shell, Git, or any other descendant process.
    if os.environ.get("AUTOMATION_TASK_PROCESS") == "1" and event in {
        "subprocess.Popen", "os.system", "os.exec", "os.spawn",
        "os.posix_spawn", "os.fork", "os.forkpty", "os.startfile", "pty.spawn",
    }:
        raise PermissionError("child-process creation is prohibited in fenced production task processes")
    if event == "open" and args:
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        writing = isinstance(mode, str) and any(char in mode for char in "wax+")
        if isinstance(flags, int):
            writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            authorize_write_path(args[0])
            _record_write_trace(args[0], "open")
        return
    if event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate", "os.utime"} and args:
        path = args[0]
        if isinstance(path, int):
            raise PermissionError("descriptor-based filesystem mutations are denied by the production write guard")
        authorize_write_path(path)
        _record_write_trace(path, event)
        return
    if event in {"os.rename", "os.replace"} and len(args) >= 2:
        authorize_write_path(args[0])
        authorize_write_path(args[1])
        _record_write_trace(args[0], event + ":source")
        _record_write_trace(args[1], event + ":destination")
        return
    if event in {"os.symlink", "os.link"} and len(args) >= 2:
        if event == "os.link":
            authorize_write_path(args[0])
        authorize_write_path(args[1])
        _record_write_trace(args[1], event)


def install_write_guard() -> bool:
    """Install once per process; write checks activate only for authorized production runs."""
    global _INSTALLED
    if _INSTALLED:
        return True
    sys.dont_write_bytecode = True
    sys.addaudithook(_audit_hook)
    _INSTALLED = True
    return True
