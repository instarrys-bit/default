#!/usr/bin/env python3
"""Fail-closed filesystem write guard for Watchdog-owned production runs."""
from __future__ import annotations
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PATHS = {"shadowrocket/ss.conf"}
_INSTALLED = False


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
        raise PermissionError("owner-managed protected file is read-only: shadowrocket/ss.conf")
    return resolved_value if resolved_value not in {"", "."} else None


def authorize_write_path(path) -> None:
    """Reject the owner config unconditionally and fence every repo-local write."""
    relative = _repo_relative(path)
    if relative is None:
        # A pre-existing external hard link to the protected config has a different
        # pathname but the same inode; deny it as well.
        try:
            candidate_stat = Path(os.fsdecode(path)).stat()
            protected_stat = (ROOT / "shadowrocket" / "ss.conf").stat()
            if (candidate_stat.st_dev, candidate_stat.st_ino) == (protected_stat.st_dev, protected_stat.st_ino):
                raise PermissionError("owner-managed protected file is read-only: shadowrocket/ss.conf")
        except FileNotFoundError:
            pass
        return
    if relative in PROTECTED_PATHS:
        raise PermissionError(f"owner-managed protected file is read-only: {relative}")
    if os.environ.get("AUTOMATION_REQUIRE_RESOURCE_LEASE") != "1":
        return
    from resource_lease_runtime import assert_resource_lease_from_environment
    assert_resource_lease_from_environment(relative)


def _audit_hook(event: str, args: tuple) -> None:
    if event == "open" and args:
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        writing = isinstance(mode, str) and any(char in mode for char in "wax+")
        if isinstance(flags, int):
            writing = writing or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        if writing:
            authorize_write_path(args[0])
        return
    if event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate", "os.utime"} and args:
        path = args[0]
        if isinstance(path, int):
            raise PermissionError("descriptor-based filesystem mutations are denied by the production write guard")
        authorize_write_path(path)
        return
    if event in {"os.rename", "os.replace"} and len(args) >= 2:
        authorize_write_path(args[0])
        authorize_write_path(args[1])
        return
    if event in {"os.symlink", "os.link"} and len(args) >= 2:
        if event == "os.link":
            authorize_write_path(args[0])
        authorize_write_path(args[1])


def install_write_guard() -> bool:
    """Install once per process; write checks activate only for authorized production runs."""
    global _INSTALLED
    if _INSTALLED:
        return True
    sys.dont_write_bytecode = True
    sys.addaudithook(_audit_hook)
    _INSTALLED = True
    return True
