#!/usr/bin/env python3
"""Safely restore only high-volume automation state from a prior audit artifact."""
from __future__ import annotations
import argparse, json, tarfile
from pathlib import Path, PurePosixPath

ALLOWED_FILES = {
    "data/domain_candidates.json", "data/candidates.json", "data/source_pending.json",
    "data/primary_snapshot.txt", "data/secondary_snapshot.txt",
    "sources/domain_reviews.json", "sources/review_cursor.json", "sources/rule_provenance.json",
}
ALLOWED_DIR_PREFIXES = ("data/source_snapshots/",)
REQUIRED_FILES = {"data/candidates.json", "sources/domain_reviews.json"}

def allowed(name: str) -> bool:
    normalized = str(PurePosixPath(name))
    return normalized in ALLOWED_FILES or any(normalized.startswith(p) for p in ALLOWED_DIR_PREFIXES)

def restore_state(archive: Path, root: Path) -> dict:
    root = root.resolve()
    restored, total_bytes, seen_required = [], 0, set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            if not allowed(name):
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe state archive path: {name}")
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported state archive entry: {name}")
            destination = (root / Path(*path.parts)).resolve()
            if destination != root and root not in destination.parents:
                raise ValueError(f"state path escapes repository: {name}")
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            source = tar.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read state archive entry: {name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".restore-tmp")
            with source, temporary.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk: break
                    output.write(chunk)
            temporary.replace(destination)
            restored.append(name)
            total_bytes += member.size
            if name in REQUIRED_FILES: seen_required.add(name)
    missing = REQUIRED_FILES - seen_required
    if missing:
        raise ValueError("state artifact is incomplete; missing: " + ", ".join(sorted(missing)))
    return {"restored_files": len(restored), "restored_bytes": total_bytes, "paths": sorted(restored)}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--root", default=".", type=Path)
    args = parser.parse_args()
    print(json.dumps(restore_state(args.archive, args.root), ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
