#!/usr/bin/env python3
"""Safely restore only allowlisted automation state, including JSONL shard sets."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()

import argparse, json, tarfile
from pathlib import Path, PurePosixPath

ALLOWED_FILES = {
    "data/domain_candidates.json", "data/domain_candidates.json.manifest.json",
    "data/candidates.json", "data/candidates.json.manifest.json",
    "data/source_pending.json", "data/primary_snapshot.txt", "data/secondary_snapshot.txt",
    "sources/domain_reviews.json", "sources/domain_reviews.json.manifest.json",
    "sources/review_cursor.json", "sources/rule_provenance.json",
    "sources/rule_provenance.json.manifest.json",
    "sources/discovered_sources.json", "sources/discovered_sources.json.manifest.json",
    "sources/source_assessments.json", "sources/source_assessments.json.manifest.json",
    "sources/source_candidates.json", "sources/source_candidates.json.manifest.json",
}
ALLOWED_DIR_PREFIXES = (
    "data/source_snapshots/",
    "data/domain_candidates.json.parts-",
    "data/candidates.json.parts-",
    "sources/domain_reviews.json.parts-",
    "sources/rule_provenance.json.parts-",
    "sources/discovered_sources.json.parts-",
    "sources/source_assessments.json.parts-",
    "sources/source_candidates.json.parts-",
)
REQUIRED_ANY_GROUPS = (
    {"data/candidates.json", "data/candidates.json.manifest.json"},
    {"sources/domain_reviews.json", "sources/domain_reviews.json.manifest.json"},
)
PUBLISH_FILES = {
    "sources/policy.json", "sources/domain_sources.json", "sources/source_activation_log.json",
    "sources/policy_source_overlap.json", "sources/discovered_sources.json",
    "sources/discovered_sources.json.manifest.json", "sources/source_assessments.json",
    "sources/source_assessments.json.manifest.json", "sources/source_candidates.json",
    "sources/source_candidates.json.manifest.json",
    "reports/project-status.md", "reports/project-status.json",
    "reports/automation/heartbeat.json", "reports/automation/state_store.json",
    "reports/external-domain-audit.md", "reports/config-drift-audit.md", "reports/config-drift-audit.json",
    "reports/ruleset-reference-audit.md", "reports/ruleset-reference-audit.json",
    "reports/ruleset-config-overlap-audit.md", "reports/ruleset-config-overlap-audit.json",
    "reports/ruleset-config-conflict-sync.md", "reports/ruleset-config-conflict-sync.json",
    "reports/source-lineage-audit.json", "reports/source-discovery.md", "reports/source-assessment.md",
    "reports/source-candidate-matrix.md", "reports/source-activation.md", "reports/policy-source-overlap.md",
}
PUBLISH_DIR_PREFIXES = (
    "reports/lifecycle/", "rulesets/",
    "sources/discovered_sources.json.parts-", "sources/source_assessments.json.parts-",
    "sources/source_candidates.json.parts-",
)


def allowed(name: str) -> bool:
    normalized = str(PurePosixPath(name))
    return normalized in ALLOWED_FILES or any(normalized.startswith(p) for p in ALLOWED_DIR_PREFIXES)


def restore_state(archive: Path, root: Path) -> dict:
    root = root.resolve()
    restored, total_bytes, seen = [], 0, set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            name = member.name
            if not allowed(name):
                continue
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe state archive path: {name}")
            # GNU tar encodes a repeated identical input path as a self-hardlink.
            # Accept only that exact legacy duplicate after its regular file was
            # already restored; reject all other links and duplicate regular entries.
            if member.islnk():
                if member.linkname == name and name in seen:
                    continue
                raise ValueError(f"unsupported state archive entry: {name}")
            if member.issym() or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported state archive entry: {name}")
            if name in seen:
                raise ValueError(f"duplicate state archive entry: {name}")
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
                    if not chunk:
                        break
                    output.write(chunk)
            temporary.replace(destination)
            restored.append(name)
            seen.add(name)
            total_bytes += member.size

    missing = [sorted(group) for group in REQUIRED_ANY_GROUPS if not (group & seen)]
    if missing:
        labels = [" or ".join(group) for group in missing]
        raise ValueError("state artifact is incomplete; missing one of: " + "; ".join(labels))
    return {"restored_files": len(restored), "restored_bytes": total_bytes, "paths": sorted(restored)}



def publish_allowed(name: str) -> bool:
    normalized = str(PurePosixPath(name.rstrip("/")))
    return normalized in PUBLISH_FILES or any(normalized.startswith(prefix) for prefix in PUBLISH_DIR_PREFIXES)


def restore_publish_outputs(archive: Path, root: Path) -> dict:
    """Restore only explicitly publishable outputs, under the caller's live write fence."""
    root = root.resolve()
    restored, total_bytes = [], 0
    with tarfile.open(archive, "r:gz") as tar:
        selected = []
        seen = set()
        # Validate the complete archive before the first repository mutation.
        for member in tar.getmembers():
            raw_name = member.name
            path = PurePosixPath(raw_name.rstrip("/"))
            if path.is_absolute() or not path.parts or ".." in path.parts:
                raise ValueError(f"unsafe publish archive path: {raw_name}")
            name = path.as_posix()
            if name == "shadowrocket/ss.conf":
                raise ValueError("publish artifact contains owner-managed read-only config")
            if member.islnk():
                if member.linkname == raw_name and name in seen:
                    continue
                raise ValueError(f"unsupported publish archive link: {raw_name}")
            if member.issym() or not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported publish archive entry: {raw_name}")
            if not publish_allowed(name):
                continue
            if name in seen:
                raise ValueError(f"duplicate publish archive entry: {name}")
            seen.add(name)
            destination = (root / Path(*path.parts)).resolve(strict=False)
            if destination != root and root not in destination.parents:
                raise ValueError(f"publish path escapes repository: {name}")
            selected.append((member, name, path, destination))

        for member, name, path, destination in selected:
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            source = tar.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read publish archive entry: {name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".publish-tmp")
            with source, temporary.open("wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            temporary.replace(destination)
            restored.append(name)
            total_bytes += member.size

    for base in ("sources/discovered_sources.json", "sources/source_assessments.json", "sources/source_candidates.json"):
        if base + ".manifest.json" in seen and base not in seen:
            (root / base).unlink(missing_ok=True)
    return {"restored_files": len(restored), "restored_bytes": total_bytes, "paths": sorted(restored)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--root", default=".", type=Path)
    parser.add_argument("--publish-outputs", action="store_true")
    args = parser.parse_args()
    result = restore_publish_outputs(args.archive, args.root) if args.publish_outputs else restore_state(args.archive, args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
