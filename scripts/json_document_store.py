#!/usr/bin/env python3
"""Transparent JSON storage with bounded JSONL shards for growing ledgers."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 50_000_000
SHARD_TARGET_BYTES = 45_000_000
MANIFEST_SUFFIX = ".manifest.json"


def manifest_path(path: Path) -> Path:
    return path.with_name(path.name + MANIFEST_SUFFIX)


def _compact_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _assert_document_lease(path: Path, required: bool) -> None:
    if not required:
        return
    from resource_lease_runtime import assert_resource_lease_from_environment
    logical_path=path
    if logical_path.name.endswith(".manifest.json"):
        logical_path=logical_path.with_name(logical_path.name[:-len(".manifest.json")])
    assert_resource_lease_from_environment(logical_path.relative_to(Path(__file__).resolve().parents[1]).as_posix())


def _atomic_write(path: Path, data: bytes, *, lease_required: bool = False) -> None:
    _assert_document_lease(path, lease_required)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_document_lease(path, lease_required)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            _assert_document_lease(path, lease_required)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _assert_document_lease(path, lease_required)
        os.replace(temporary, path)
    except Exception:
        try:
            _assert_document_lease(path, lease_required)
        except Exception:
            pass  # Preserve the temporary file rather than mutate without a valid fence.
        else:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        raise



def iter_document_records(path: Path, collection_key: str):
    """Yield records without materializing the complete JSONL-sharded collection."""
    path = Path(path)
    manifest_file = manifest_path(path)
    if not manifest_file.exists():
        if not path.exists():
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get(collection_key, [])
        if not isinstance(records, list):
            raise ValueError(f"document collection {collection_key!r} is not a list: {path}")
        yield from records
        return

    if manifest_file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"shard manifest exceeds {MAX_FILE_BYTES} bytes: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("format") != "jsonl-shards-v1":
        raise ValueError(f"unsupported shard manifest: {manifest_file}")
    if manifest.get("logical_path") != path.name or manifest.get("collection_key") != collection_key:
        raise ValueError(f"shard manifest identity mismatch: {manifest_file}")
    directory = str(manifest.get("shard_directory", ""))
    if not directory or Path(directory).name != directory:
        raise ValueError(f"unsafe shard directory in {manifest_file}")
    total_records = 0
    for shard in manifest.get("shards", []):
        name = str(shard.get("file", ""))
        if not name or Path(name).name != name or not name.endswith(".jsonl"):
            raise ValueError(f"unsafe shard name in {manifest_file}: {name!r}")
        shard_path = manifest_file.parent / directory / name
        raw = shard_path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError(f"shard exceeds {MAX_FILE_BYTES} bytes: {shard_path}")
        if hashlib.sha256(raw).hexdigest() != shard.get("sha256"):
            raise ValueError(f"shard checksum mismatch: {shard_path}")
        shard_count = 0
        for line in raw.splitlines():
            if not line:
                continue
            yield json.loads(line)
            shard_count += 1
            total_records += 1
        if shard_count != int(shard.get("records", -1)):
            raise ValueError(f"shard record-count mismatch: {shard_path}")
    if total_records != int(manifest.get("record_count", -1)):
        raise ValueError(f"document record-count mismatch: {manifest_file}")


def read_document(path: Path, collection_key: str, default: dict | None = None) -> dict:
    """Read legacy JSON or verify and reconstruct a sharded document."""
    path = Path(path)
    manifest_file = manifest_path(path)
    if not manifest_file.exists():
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return default if default is not None else {collection_key: []}

    if manifest_file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"shard manifest exceeds {MAX_FILE_BYTES} bytes: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("format") != "jsonl-shards-v1":
        raise ValueError(f"unsupported shard manifest: {manifest_file}")
    if manifest.get("logical_path") != path.name or manifest.get("collection_key") != collection_key:
        raise ValueError(f"shard manifest identity mismatch: {manifest_file}")

    records = []
    for shard in manifest.get("shards", []):
        name = str(shard.get("file", ""))
        if not name or Path(name).name != name or not name.endswith(".jsonl"):
            raise ValueError(f"unsafe shard name in {manifest_file}: {name!r}")
        directory = str(manifest.get("shard_directory", ""))
        if not directory or Path(directory).name != directory:
            raise ValueError(f"unsafe shard directory in {manifest_file}")
        shard_path = manifest_file.parent / directory / name
        raw = shard_path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError(f"shard exceeds {MAX_FILE_BYTES} bytes: {shard_path}")
        if hashlib.sha256(raw).hexdigest() != shard.get("sha256"):
            raise ValueError(f"shard checksum mismatch: {shard_path}")
        rows = [line for line in raw.splitlines() if line]
        if len(rows) != int(shard.get("records", -1)):
            raise ValueError(f"shard record-count mismatch: {shard_path}")
        records.extend(json.loads(line) for line in rows)
    if len(records) != int(manifest.get("record_count", -1)):
        raise ValueError(f"document record-count mismatch: {manifest_file}")
    metadata = manifest.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"invalid metadata in {manifest_file}")
    result = dict(metadata)
    result[collection_key] = records
    return result


def write_document(path: Path, payload: dict, collection_key: str, *, lease_required: bool = False) -> dict:
    """Write one bounded JSON file, or switch atomically to immutable JSONL shards."""
    path = Path(path)
    if not isinstance(payload, dict) or not isinstance(payload.get(collection_key), list):
        raise ValueError(f"document must contain a list at {collection_key!r}")
    records = payload[collection_key]
    metadata = {key: value for key, value in payload.items() if key != collection_key}
    manifest_file = manifest_path(path)
    already_sharded = manifest_file.exists()

    # Estimate compact size without constructing an unbounded serialized document.
    metadata_bytes = _compact_bytes(metadata)
    if len(metadata_bytes) > MAX_FILE_BYTES:
        raise ValueError("document metadata exceeds the 50 MB single-file limit")
    estimate = len(metadata_bytes) + len(collection_key.encode("utf-8")) + 16
    for record in records:
        estimate += len(_compact_bytes(record)) + 1
        if estimate > MAX_FILE_BYTES:
            break

    if estimate <= MAX_FILE_BYTES and not already_sharded:
        legacy = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(legacy) <= MAX_FILE_BYTES:
            _atomic_write(path, legacy, lease_required=lease_required)
            return {"storage": "json", "records": len(records), "bytes": len(legacy), "shards": 0}

    _assert_document_lease(path, lease_required)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_document_lease(path, lease_required)
    staging = Path(tempfile.mkdtemp(prefix=path.name + ".parts.tmp-", dir=str(path.parent)))
    shard_entries = []
    shard_buffer = bytearray()
    shard_index = 0
    total_shard_bytes = 0
    digest = hashlib.sha256()
    digest.update(metadata_bytes)
    digest.update(collection_key.encode("utf-8"))

    def flush_shard() -> None:
        nonlocal shard_index, shard_buffer, total_shard_bytes
        if not shard_buffer:
            return
        if len(shard_buffer) > MAX_FILE_BYTES:
            raise ValueError("internal shard sizing error")
        name = f"part-{shard_index:06d}.jsonl"
        raw = bytes(shard_buffer)
        _assert_document_lease(path, lease_required)
        (staging / name).write_bytes(raw)
        shard_entries.append({
            "file": name,
            "records": len(raw.splitlines()),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
        total_shard_bytes += len(raw)
        shard_index += 1
        shard_buffer = bytearray()

    try:
        for record in records:
            line = _compact_bytes(record) + b"\n"
            if len(line) > MAX_FILE_BYTES:
                raise ValueError("one record exceeds the 50 MiB single-file limit")
            digest.update(line)
            if shard_buffer and len(shard_buffer) + len(line) > SHARD_TARGET_BYTES:
                flush_shard()
            shard_buffer.extend(line)
        flush_shard()

        version = digest.hexdigest()[:16]
        shard_directory = path.name + ".parts-" + version
        final_directory = path.parent / shard_directory
        if final_directory.exists():
            # Same content-addressed version is already complete and may be live.
            _assert_document_lease(path, lease_required)
            shutil.rmtree(staging)
        else:
            _assert_document_lease(path, lease_required)
            os.replace(staging, final_directory)

        manifest = {
            "schema_version": 1,
            "format": "jsonl-shards-v1",
            "logical_path": path.name,
            "collection_key": collection_key,
            "record_count": len(records),
            "total_shard_bytes": total_shard_bytes,
            "max_file_bytes": MAX_FILE_BYTES,
            "shard_directory": shard_directory,
            "metadata": metadata,
            "shards": shard_entries,
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(manifest_bytes) > MAX_FILE_BYTES:
            raise ValueError("shard manifest exceeds the 50 MB single-file limit")
        _atomic_write(manifest_file, manifest_bytes, lease_required=lease_required)
        # The manifest is authoritative only after its atomic replacement.
        if path.exists():
            _assert_document_lease(path, lease_required)
            path.unlink()
        for old in path.parent.glob(path.name + ".parts-*"):
            if old.is_dir() and old.name != shard_directory:
                _assert_document_lease(path, lease_required)
                shutil.rmtree(old)
        return {"storage": "jsonl-shards-v1", "records": len(records), "bytes": total_shard_bytes, "shards": len(shard_entries)}
    except Exception:
        if staging.exists():
            try:
                _assert_document_lease(path, lease_required)
            except Exception:
                pass  # Leave an orphaned staging directory rather than clean up without the live fence.
            else:
                shutil.rmtree(staging, ignore_errors=True)
        raise
