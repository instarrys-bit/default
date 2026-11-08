#!/usr/bin/env python3
"""Safely restore only allowlisted automation state, including JSONL shard sets."""
from __future__ import annotations

import argparse, hashlib, json, tarfile
from pathlib import Path, PurePosixPath
from resource_lease_runtime import assert_resource_lease_from_environment

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
PUBLISH_FILES = set()
PUBLISH_DIR_PREFIXES = ("rulesets/",)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def verify_managed_config_baseline(root: Path) -> dict:
    """Fail closed unless the checked-out owner config matches its committed baseline."""
    policy_path = root / "sources" / "policy.json"
    config_path = root / "modules" / "uu.conf"
    if not policy_path.is_file() or not config_path.is_file():
        raise ValueError("publish preflight requires sources/policy.json and modules/uu.conf")
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("publish preflight cannot read the managed-config policy") from exc
    guard = policy.get("managed_config_guard")
    if not isinstance(guard, dict) or guard.get("path") != "modules/uu.conf":
        raise ValueError("publish preflight requires modules/uu.conf as the sole managed config baseline")
    protection = guard.get("content_protection")
    if (guard.get("content_immutable_to_automation") is not True
            or not isinstance(protection, dict)
            or protection.get("automation_may_modify_content") is not False):
        raise ValueError("publish preflight refuses a managed config without an explicit read-only protection policy")
    expected = guard.get("approved_git_blob_sha")
    if not isinstance(expected, str) or len(expected) != 40 or any(ch not in "0123456789abcdef" for ch in expected):
        raise ValueError("publish preflight found an invalid approved uu.conf Git blob SHA")
    actual = git_blob_sha(config_path.read_bytes())
    if actual != expected:
        raise ValueError(
            "publish preflight blocked before repository mutation: "
            f"modules/uu.conf blob SHA {actual} differs from approved baseline {expected}; "
            "register the owner-verified baseline on main first, then rerun the audit"
        )
    return {"path": "modules/uu.conf", "git_blob_sha": actual}


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
    baseline_before = verify_managed_config_baseline(root)
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
            if name == "modules/uu.conf":
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
                continue
            assert_resource_lease_from_environment(name)
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
    baseline_after = verify_managed_config_baseline(root)
    if baseline_after != baseline_before:
        raise ValueError("managed uu.conf baseline changed during ruleset publication restore")
    return {"restored_files": len(restored), "restored_bytes": total_bytes, "paths": sorted(restored), "config_baseline": baseline_after}


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
