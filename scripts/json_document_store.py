#!/usr/bin/env python3
"""Transparent JSON document storage with bounded JSONL shards.

Legacy JSON remains readable. Once a document needs sharding, it stays sharded
so readers never race between two storage formats during normal operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 50 * 1024 * 1024
SHARD_TARGET_BYTES = 45 * 1024 * 1024
MANIFEST_SUFFIX = ".manifest.json"


def manifest_path(path: Path) -> Path:
    return path.with_name(path.name + MANIFEST_SUFFIX)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def read_document(path: Path, collection_key: str, default: dict | None = None) -> dict:
    """Read a legacy JSON file or verify and reconstruct its sharded equivalent."""
    path = Path(path)
    manifest_file = manifest_path(path)
    if not manifest_file.exists():
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return default if default is not None else {collection_key: []}

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("format") != "jsonl-shards-v1":
        raise ValueError(f"unsupported shard manifest: {manifest_file}")
    if manifest.get("logical_path") != path.name or manifest.get("collection_key") != collection_key:
        raise ValueError(f"shard manifest identity mismatch: {manifest_file}")

    records = []
    total_bytes = 0
    for shard in manifest.get("shards", []):
        name = str(shard.get("file", ""))
        if not name or Path(name).name != name or not name.endswith(".jsonl"):
            raise ValueError(f"unsafe shard name in {manifest_file}: {name!r}")
        shard_path = manifest_file.parent / str(manifest["shard_directory"]) / name
        raw = shard_path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError(f"shard exceeds {MAX_FILE_BYTES} bytes: {shard_path}")
        if hashlib.sha256(raw).hexdigest() != shard.get("sha256"):
            raise ValueError(f"shard checksum mismatch: {shard_path}")
        rows = [line for line in raw.splitlines() if line]
        if len(rows) != int(shard.get("records", -1)):
            raise ValueError(f"shard record-count mismatch: {shard_path}")
        records.extend(json.loads(line) for line in rows)
        total_bytes += len(raw)
    if len(records) != int(manifest.get("record_count", -1)):
        raise ValueError(f"document record-count mismatch: {manifest_file}")
    metadata = manifest.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"invalid metadata in {manifest_file}")
    result = dict(metadata)
    result[collection_key] = records
    return result


def write_document(path: Path, payload: dict, collection_key: str) -> dict:
    """Atomically write legacy JSON or immutable JSONL shards plus a manifest."""
    path = Path(path)
    if not isinstance(payload, dict) or not isinstance(payload.get(collection_key), list):
        raise ValueError(f"document must contain a list at {collection_key!r}")
    records = payload[collection_key]
    metadata = {key: value for key, value in payload.items() if key != collection_key}
    legacy = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    already_sharded = manifest_path(path).exists()

    if len(legacy) <= MAX_FILE_BYTES and not already_sharded:
        _atomic_write(path, legacy)
        return {"storage": "json", "records": len(records), "bytes": len(legacy), "shards": 0}

    path.parent.mkdir(parents=True, exist_ok=True)
    version = hashlib.sha256(legacy).hexdigest()[:16]
    shard_directory = path.name + ".parts-" + version
    staging = Path(tempfile.mkdtemp(prefix=shard_directory + ".tmp-", dir=str(path.parent)))
    shard_entries = []
    shard_buffer = bytearray()
    shard_index = 0
    total_shard_bytes = 0

    def flush_shard() -> None:
        nonlocal shard_index, shard_buffer, total_shard_bytes
        if not shard_buffer:
            return
        if len(shard_buffer) > MAX_FILE_BYTES:
            raise ValueError("internal shard sizing error")
        name = f"part-{shard_index:06d}.jsonl"
        raw = bytes(shard_buffer)
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
            line = _json_bytes(record) + b"\n"
            if len(line) > MAX_FILE_BYTES:
                raise ValueError("one record exceeds the 50 MiB single-file limit")
            if shard_buffer and len(shard_buffer) + len(line) > SHARD_TARGET_BYTES:
                flush_shard()
            shard_buffer.extend(line)
        flush_shard()

        final_directory = path.parent / shard_directory
        if final_directory.exists():
            shutil.rmtree(final_directory)
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
        _atomic_write(manifest_path(path), (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        # Manifest is now authoritative; removing the legacy monolith is safe.
        if path.exists():
            path.unlink()
        for old in path.parent.glob(path.name + ".parts-*"):
            if old.is_dir() and old.name != shard_directory:
                shutil.rmtree(old)
        return {"storage": "jsonl-shards-v1", "records": len(records), "bytes": total_shard_bytes, "shards": len(shard_entries)}
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
