#!/usr/bin/env python3
"""Restore only RULE-SET artifacts into the publication checkout."""
from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_FILES = 10000


def restore_publish_outputs(archive: Path, root: Path) -> dict:
    """Validate the complete archive, then atomically restore only rulesets/ files."""
    root = root.resolve()
    selected = []
    seen = set()
    total_bytes = 0
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if len(members) > MAX_FILES:
            raise ValueError("ruleset artifact contains too many entries")
        for member in members:
            raw_name = member.name
            path = PurePosixPath(raw_name.rstrip("/"))
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError(f"unsafe ruleset archive path: {raw_name}")
            name = path.as_posix()
            if not (name == "rulesets" or name.startswith("rulesets/")):
                raise ValueError(f"non-ruleset path in production artifact: {name}")
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported ruleset archive entry: {raw_name}")
            if name in seen:
                raise ValueError(f"duplicate ruleset archive entry: {name}")
            seen.add(name)
            destination = (root / Path(*path.parts)).resolve(strict=False)
            if destination != root and root not in destination.parents:
                raise ValueError(f"ruleset path escapes publication checkout: {name}")
            if member.isfile():
                total_bytes += member.size
                if total_bytes > MAX_ARCHIVE_BYTES:
                    raise ValueError("ruleset artifact exceeds the size limit")
            selected.append((member, name, destination))

        restored = []
        for member, name, destination in selected:
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            source = tar.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read ruleset archive entry: {name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".ruleset-restore-tmp")
            with source, temporary.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            temporary.replace(destination)
            restored.append(name)
    return {"restored_files": len(restored), "restored_bytes": total_bytes, "paths": sorted(restored)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--publish-outputs", action="store_true", required=True)
    args = parser.parse_args()
    result = restore_publish_outputs(args.archive, args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
