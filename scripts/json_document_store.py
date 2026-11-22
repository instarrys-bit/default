#!/usr/bin/env python3
"""Transparent JSON storage with bounded JSONL shards for growing ledgers."""
from __future__ import annotations


import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
import zlib
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 50_000_000
SHARD_TARGET_BYTES = 45_000_000
MANIFEST_SUFFIX = ".manifest.json"


def manifest_path(path: Path) -> Path:
    return path.with_name(path.name + MANIFEST_SUFFIX)


def delta_manifest_path(path: Path) -> Path:
    return path.with_name(path.name + ".delta.manifest.json")


def _read_delta_manifest(path: Path, collection_key: str) -> dict | None:
    manifest_file = delta_manifest_path(path)
    if not manifest_file.exists():
        return None
    if manifest_file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"delta manifest exceeds {MAX_FILE_BYTES} bytes: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != 1
            or manifest.get("format") != "jsonl-delta-v1"
            or manifest.get("logical_path") != path.name
            or manifest.get("collection_key") != collection_key):
        raise ValueError(f"delta manifest identity or format mismatch: {manifest_file}")
    directory = str(manifest.get("delta_directory", ""))
    if not directory or Path(directory).name != directory:
        raise ValueError(f"unsafe delta directory in {manifest_file}")
    if not isinstance(manifest.get("metadata", {}), dict) or not isinstance(manifest.get("segments", []), list):
        raise ValueError(f"invalid delta manifest collections: {manifest_file}")
    return manifest


def _iter_delta_records(path: Path, collection_key: str, after_checkpoint: int = -1):
    manifest = _read_delta_manifest(path, collection_key)
    if not manifest:
        return
    directory = str(manifest["delta_directory"])
    for segment in manifest.get("segments", []):
        if int(segment.get("checkpoint_index", -1)) <= after_checkpoint:
            continue
        name = str(segment.get("file", ""))
        if not name or Path(name).name != name or not name.endswith(".jsonl"):
            raise ValueError(f"unsafe delta segment name in {path}: {name!r}")
        segment_path = path.parent / directory / name
        raw = segment_path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError(f"delta segment exceeds {MAX_FILE_BYTES} bytes: {segment_path}")
        if hashlib.sha256(raw).hexdigest() != segment.get("sha256"):
            raise ValueError(f"delta segment checksum mismatch: {segment_path}")
        count = 0
        for line in raw.splitlines():
            if line:
                yield json.loads(line)
                count += 1
        if count != int(segment.get("records", -1)):
            raise ValueError(f"delta segment record-count mismatch: {segment_path}")


def document_delta_watermark(path: Path, collection_key: str) -> int:
    manifest = _read_delta_manifest(Path(path), collection_key)
    if not manifest:
        return -1
    return max((int(item.get("checkpoint_index", -1)) for item in manifest.get("segments", [])), default=-1)


def _compact_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _verified_shard_payload(
    raw: bytes, shard: dict, shard_path: Path, compressed: bool,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_uncompressed_bytes: int | None = None,
) -> bytes:
    """Verify one physical shard and boundedly decode its logical JSONL payload."""
    file_limit = min(MAX_FILE_BYTES, int(max_file_bytes))
    if file_limit <= 0:
        raise ValueError("shard file limit must be positive")
    if len(raw) > file_limit:
        raise ValueError(f"shard exceeds {file_limit} bytes: {shard_path}")
    if hashlib.sha256(raw).hexdigest() != shard.get("sha256"):
        raise ValueError(f"shard checksum mismatch: {shard_path}")
    if len(raw) != int(shard.get("bytes", -1)):
        raise ValueError(f"shard byte-count mismatch: {shard_path}")
    if not compressed:
        return raw

    expected = int(shard.get("uncompressed_bytes", -1))
    if expected < 0:
        raise ValueError(f"invalid shard uncompressed byte count: {shard_path}")
    uncompressed_limit = file_limit if max_uncompressed_bytes is None else int(max_uncompressed_bytes)
    if uncompressed_limit <= 0:
        raise ValueError("shard uncompressed byte limit must be positive")
    if expected > uncompressed_limit:
        raise ValueError(f"uncompressed shard exceeds {uncompressed_limit} bytes: {shard_path}")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        decoded = decoder.decompress(raw, uncompressed_limit + 1)
    except zlib.error as exc:
        raise ValueError(f"compressed shard cannot be decoded: {shard_path}") from exc
    if len(decoded) > uncompressed_limit or decoder.unconsumed_tail:
        raise ValueError(f"uncompressed shard exceeds {uncompressed_limit} bytes: {shard_path}")
    if not decoder.eof:
        raise ValueError(f"compressed shard is truncated: {shard_path}")
    if decoder.unused_data:
        raise ValueError(f"compressed shard has trailing data: {shard_path}")
    if len(decoded) != expected:
        raise ValueError(f"shard uncompressed byte-count mismatch: {shard_path}")
    return decoded


def _gzip_shard(raw: bytes) -> bytes:
    """Produce reproducible gzip bytes for content-addressed shard storage."""
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as stream:
        stream.write(raw)
    return buffer.getvalue()


def _validate_sharded_document_total(manifest: dict, collection_key: str) -> int:
    """Verify declared shard sizes and the stored-document byte budget."""
    metadata = manifest.get("metadata", {})
    shards = manifest.get("shards", [])
    if not isinstance(metadata, dict) or not isinstance(shards, list):
        raise ValueError("invalid shard manifest totals")
    shard_bytes = 0
    for shard in shards:
        if not isinstance(shard, dict):
            raise ValueError("invalid shard manifest entry")
        size = int(shard.get("bytes", -1))
        if size < 0:
            raise ValueError("invalid shard byte count")
        shard_bytes += size
    declared_shard_bytes = manifest.get("total_shard_bytes")
    if declared_shard_bytes is not None and int(declared_shard_bytes) != shard_bytes:
        raise ValueError("document total shard byte-count mismatch")
    total_document_bytes = (
        len(_compact_bytes(metadata)) + len(collection_key.encode("utf-8")) + 16 + shard_bytes
    )
    declared_total_bytes = manifest.get("total_document_bytes")
    if declared_total_bytes is not None and int(declared_total_bytes) != total_document_bytes:
        raise ValueError("document total byte-count mismatch")
    total_limit = manifest.get("max_total_bytes")
    if total_limit is not None and total_document_bytes > int(total_limit):
        raise ValueError(
            f"document exceeds the {int(total_limit)}-byte total document limit "
            f"({total_document_bytes} bytes)"
        )
    return total_document_bytes


def _assert_document_lease(path: Path, required: bool = True) -> None:
    """Require a live fence for every repository mutation; caller flags cannot bypass it.

    Runner-local paths outside the repository remain writable without a repository
    lease. Repository paths are checked against the actual base, manifest, shard,
    staging or cleanup target so symlink and hard-link aliases are rejected. The
    resource lease matcher maps child paths to the parent logical document key.
    The legacy required argument remains accepted for caller compatibility.
    """
    del required
    from resource_lease_runtime import assert_resource_lease_for_repository_path

    repository_root = Path(__file__).resolve().parents[1]
    lexical_path = Path(path)
    if not lexical_path.is_absolute():
        lexical_path = Path.cwd() / lexical_path
    normalized_path = Path(os.path.abspath(lexical_path))
    if repository_root in lexical_path.parents and normalized_path != lexical_path:
        raise ValueError("repository document path may not contain traversal components")
    try:
        relative_path = normalized_path.relative_to(repository_root)
    except ValueError:
        # A runner-local path is allowed only if it does not resolve through an
        # external symlink into the repository.
        try:
            normalized_path.resolve(strict=False).relative_to(repository_root)
        except ValueError:
            return
        raise ValueError("external document path may not alias into the repository")
    assert_resource_lease_for_repository_path(repository_root, relative_path.as_posix())


def _atomic_write(path: Path, data: bytes, *, lease_required: bool = True) -> None:
    _assert_document_lease(path, lease_required)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_document_lease(path, lease_required)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    temporary_path = Path(temporary)
    try:
        _assert_document_lease(temporary_path, lease_required)
        with os.fdopen(fd, "wb") as stream:
            _assert_document_lease(temporary_path, lease_required)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _assert_document_lease(temporary_path, lease_required)
        _assert_document_lease(path, lease_required)
        os.replace(temporary, path)
    except Exception:
        try:
            _assert_document_lease(temporary_path, lease_required)
        except Exception:
            pass  # Preserve the temporary file rather than mutate without a valid fence.
        else:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        raise



def iter_document_records(path: Path, collection_key: str):
    """Yield base records followed by committed delta updates in checkpoint order."""
    path = Path(path)
    manifest_file = manifest_path(path)
    if not manifest_file.exists():
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload.get(collection_key, [])
            if not isinstance(records, list):
                raise ValueError(f"document collection {collection_key!r} is not a list: {path}")
            yield from records
            watermark = int(payload.get("_delta_compacted_through", -1))
    else:
        if manifest_file.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"shard manifest exceeds {MAX_FILE_BYTES} bytes: {manifest_file}")
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1 or manifest.get("format") not in {"jsonl-shards-v1", "jsonl-gzip-shards-v1"}:
            raise ValueError(f"unsupported shard manifest: {manifest_file}")
        if manifest.get("logical_path") != path.name or manifest.get("collection_key") != collection_key:
            raise ValueError(f"shard manifest identity mismatch: {manifest_file}")
        _validate_sharded_document_total(manifest, collection_key)
        compressed = manifest.get("format") == "jsonl-gzip-shards-v1"
        directory = str(manifest.get("shard_directory", ""))
        if not directory or Path(directory).name != directory:
            raise ValueError(f"unsafe shard directory in {manifest_file}")
        total_records = 0
        for shard in manifest.get("shards", []):
            name = str(shard.get("file", ""))
            if not name or Path(name).name != name or not (name.endswith(".jsonl") or name.endswith(".jsonl.gz")):
                raise ValueError(f"unsafe shard name in {manifest_file}: {name!r}")
            shard_path = manifest_file.parent / directory / name
            raw = _verified_shard_payload(
                shard_path.read_bytes(), shard, shard_path, compressed,
                int(manifest.get("max_file_bytes", MAX_FILE_BYTES)),
                int(manifest.get("max_uncompressed_file_bytes", manifest.get("max_file_bytes", MAX_FILE_BYTES))),
            )
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
        metadata = manifest.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"invalid metadata in {manifest_file}")
        watermark = int(metadata.get("_delta_compacted_through", -1))
    if not manifest_file.exists() and not path.exists():
        watermark = -1
    yield from _iter_delta_records(path, collection_key, watermark)

def read_document(path: Path, collection_key: str, default: dict | None = None) -> dict:
    """Read legacy JSON or verify and reconstruct a sharded document."""
    path = Path(path)
    manifest_file = manifest_path(path)
    if not manifest_file.exists():
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8"))
        else:
            result = dict(default) if default is not None else {collection_key: []}
        if not isinstance(result.get(collection_key, []), list):
            raise ValueError(f"document collection {collection_key!r} is not a list: {path}")
        result.setdefault(collection_key, [])
        delta = _read_delta_manifest(path, collection_key)
        if delta:
            result.update(delta.get("metadata", {}))
            result[collection_key].extend(_iter_delta_records(
                path, collection_key, int(result.get("_delta_compacted_through", -1))
            ))
        return result

    if manifest_file.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"shard manifest exceeds {MAX_FILE_BYTES} bytes: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("format") not in {"jsonl-shards-v1", "jsonl-gzip-shards-v1"}:
        raise ValueError(f"unsupported shard manifest: {manifest_file}")
    if manifest.get("logical_path") != path.name or manifest.get("collection_key") != collection_key:
        raise ValueError(f"shard manifest identity mismatch: {manifest_file}")
    _validate_sharded_document_total(manifest, collection_key)

    compressed = manifest.get("format") == "jsonl-gzip-shards-v1"
    records = []
    for shard in manifest.get("shards", []):
        name = str(shard.get("file", ""))
        if not name or Path(name).name != name or not (name.endswith(".jsonl") or name.endswith(".jsonl.gz")):
            raise ValueError(f"unsafe shard name in {manifest_file}: {name!r}")
        directory = str(manifest.get("shard_directory", ""))
        if not directory or Path(directory).name != directory:
            raise ValueError(f"unsafe shard directory in {manifest_file}")
        shard_path = manifest_file.parent / directory / name
        raw = _verified_shard_payload(
                shard_path.read_bytes(), shard, shard_path, compressed,
                int(manifest.get("max_file_bytes", MAX_FILE_BYTES)),
                int(manifest.get("max_uncompressed_file_bytes", manifest.get("max_file_bytes", MAX_FILE_BYTES))),
            )
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
    delta = _read_delta_manifest(path, collection_key)
    if delta:
        result.update(delta.get("metadata", {}))
        result[collection_key].extend(_iter_delta_records(
            path, collection_key, int(result.get("_delta_compacted_through", -1))
        ))
    return result


def write_document(
    path: Path, payload: dict, collection_key: str, *, lease_required: bool = True,
    force_sharded: bool = False, max_file_bytes: int | None = None,
    shard_target_bytes: int | None = None, max_total_bytes: int | None = None,
    compress_shards: bool = False, max_uncompressed_file_bytes: int | None = None,
) -> dict:
    """Write one bounded JSON file, or switch atomically to immutable JSONL shards.

    Per-document limits allow large ledgers to use a stricter shard budget without
    changing the defaults for other callers. max_total_bytes caps stored bytes,
    including metadata and compressed or uncompressed shard payloads.
    """
    path = Path(path)
    if not isinstance(payload, dict) or not isinstance(payload.get(collection_key), list):
        raise ValueError(f"document must contain a list at {collection_key!r}")
    records = payload[collection_key]
    metadata = {key: value for key, value in payload.items() if key != collection_key}
    file_limit = MAX_FILE_BYTES if max_file_bytes is None else int(max_file_bytes)
    shard_limit = SHARD_TARGET_BYTES if shard_target_bytes is None else int(shard_target_bytes)
    uncompressed_limit = (
        file_limit if max_uncompressed_file_bytes is None
        else int(max_uncompressed_file_bytes)
    )
    total_limit = None if max_total_bytes is None else int(max_total_bytes)
    if uncompressed_limit <= 0:
        raise ValueError("uncompressed shard limit must be positive")
    if total_limit is not None and total_limit <= 0:
        raise ValueError("document total byte limit must be positive")
    if file_limit <= 0 or shard_limit <= 0 or shard_limit > file_limit:
        raise ValueError("document shard limits must be positive and shard_target_bytes <= max_file_bytes")
    manifest_file = manifest_path(path)
    already_sharded = manifest_file.exists()

    # Estimate compact size without constructing an unbounded serialized document.
    metadata_bytes = _compact_bytes(metadata)
    if len(metadata_bytes) > file_limit:
        raise ValueError(f"document metadata exceeds the {file_limit}-byte single-file limit")
    envelope_bytes = len(collection_key.encode("utf-8")) + 16
    if total_limit is not None and len(metadata_bytes) + envelope_bytes > total_limit:
        raise ValueError(
            f"document metadata exceeds the {total_limit}-byte total document limit"
        )
    estimate = len(metadata_bytes) + envelope_bytes
    for record in records:
        estimate += len(_compact_bytes(record)) + 1
        if estimate > file_limit:
            break

    if estimate <= file_limit and not already_sharded and not force_sharded:
        legacy = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(legacy) <= file_limit:
            if total_limit is not None and len(legacy) > total_limit:
                raise ValueError(
                    f"document exceeds the {total_limit}-byte total document limit ({len(legacy)} bytes)"
                )
            _atomic_write(path, legacy, lease_required=lease_required)
            return {
                "storage": "json", "records": len(records), "bytes": len(legacy),
                "total_bytes": len(legacy), "max_total_bytes": total_limit, "shards": 0,
            }

    _assert_document_lease(path, lease_required)
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_document_lease(path, lease_required)
    staging = Path(tempfile.mkdtemp(prefix=path.name + ".parts.tmp-", dir=str(path.parent)))
    shard_entries = []
    shard_buffer = bytearray()
    shard_compressed = bytearray()
    shard_compressor = None
    shard_index = 0
    total_shard_bytes = 0
    digest = hashlib.sha256()
    digest.update(metadata_bytes)
    digest.update(collection_key.encode("utf-8"))

    def flush_shard() -> None:
        nonlocal shard_index, shard_buffer, shard_compressed, shard_compressor, total_shard_bytes
        if not shard_buffer:
            return
        if len(shard_buffer) > uncompressed_limit:
            raise ValueError("internal shard uncompressed sizing error")
        raw = bytes(shard_buffer)
        if compress_shards:
            if shard_compressor is None:
                raise ValueError("compressed shard is missing its compressor")
            stored = bytes(shard_compressed) + shard_compressor.flush()
        else:
            stored = raw
        if len(stored) > file_limit:
            raise ValueError(f"stored shard exceeds the {file_limit}-byte single-file limit")
        name = f"part-{shard_index:06d}.jsonl" + (".gz" if compress_shards else "")
        shard_path = staging / name
        _assert_document_lease(shard_path, lease_required)
        shard_path.write_bytes(stored)
        entry = {
            "file": name,
            "records": len(raw.splitlines()),
            "bytes": len(stored),
            "sha256": hashlib.sha256(stored).hexdigest(),
        }
        if compress_shards:
            entry["uncompressed_bytes"] = len(raw)
        shard_entries.append(entry)
        total_shard_bytes += len(stored)
        shard_index += 1
        shard_buffer = bytearray()
        shard_compressed = bytearray()
        shard_compressor = None

    try:
        for record in records:
            line = _compact_bytes(record) + b"\n"
            if len(line) > uncompressed_limit:
                raise ValueError(
                    f"one record exceeds the {uncompressed_limit}-byte uncompressed shard limit"
                )
            digest.update(line)
            if compress_shards:
                if shard_buffer:
                    trial = shard_compressor.copy()
                    trial_output = trial.compress(line)
                    projected_size = len(shard_compressed) + len(trial_output) + len(trial.copy().flush())
                    if projected_size > shard_limit or len(shard_buffer) + len(line) > uncompressed_limit:
                        flush_shard()
                if not shard_buffer:
                    shard_compressor = zlib.compressobj(level=9, wbits=16 + zlib.MAX_WBITS)
                trial = shard_compressor.copy()
                trial_output = trial.compress(line)
                projected_size = len(shard_compressed) + len(trial_output) + len(trial.copy().flush())
                if projected_size > shard_limit:
                    raise ValueError(
                        f"one record cannot fit within the {shard_limit}-byte stored shard limit"
                    )
                shard_compressor = trial
                shard_compressed.extend(trial_output)
                shard_buffer.extend(line)
            else:
                if shard_buffer and len(shard_buffer) + len(line) > shard_limit:
                    flush_shard()
                shard_buffer.extend(line)
        flush_shard()
        total_document_bytes = len(metadata_bytes) + envelope_bytes + total_shard_bytes
        if total_limit is not None and total_document_bytes > total_limit:
            raise ValueError(
                f"document exceeds the {total_limit}-byte total document limit "
                f"({total_document_bytes} bytes)"
            )

        version = digest.hexdigest()[:16]
        shard_directory = path.name + ".parts-" + version
        final_directory = path.parent / shard_directory
        if final_directory.exists():
            # Same content-addressed version is already complete and may be live.
            _assert_document_lease(staging, lease_required)
            shutil.rmtree(staging)
        else:
            _assert_document_lease(staging, lease_required)
            _assert_document_lease(final_directory, lease_required)
            os.replace(staging, final_directory)

        manifest = {
            "schema_version": 1,
            "format": "jsonl-gzip-shards-v1" if compress_shards else "jsonl-shards-v1",
            "logical_path": path.name,
            "collection_key": collection_key,
            "record_count": len(records),
            "total_shard_bytes": total_shard_bytes,
            "total_document_bytes": total_document_bytes,
            "max_file_bytes": file_limit,
            "max_uncompressed_file_bytes": uncompressed_limit,
            "max_total_bytes": total_limit,
            "shard_directory": shard_directory,
            "metadata": metadata,
            "shards": shard_entries,
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(manifest_bytes) > file_limit:
            raise ValueError(f"shard manifest exceeds the {file_limit}-byte single-file limit")
        _atomic_write(manifest_file, manifest_bytes, lease_required=lease_required)
        # The manifest is authoritative only after its atomic replacement.
        if path.exists():
            _assert_document_lease(path, lease_required)
            path.unlink()
        for old in path.parent.glob(path.name + ".parts-*"):
            if old.is_dir() and old.name != shard_directory:
                _assert_document_lease(old, lease_required)
                shutil.rmtree(old)
        return {
            "storage": "jsonl-gzip-shards-v1" if compress_shards else "jsonl-shards-v1", "records": len(records), "bytes": total_shard_bytes,
            "total_bytes": total_document_bytes, "max_total_bytes": total_limit,
            "shards": len(shard_entries),
        }
    except Exception:
        if staging.exists():
            try:
                _assert_document_lease(staging, lease_required)
            except Exception:
                pass  # Leave an orphaned staging directory rather than clean up without the live fence.
            else:
                shutil.rmtree(staging, ignore_errors=True)
        raise

def append_document_records(
    path: Path,
    payload_metadata: dict,
    collection_key: str,
    records: list[dict],
    checkpoint_index: int,
    *,
    lease_required: bool = True,
) -> dict:
    """Append one immutable, checksummed review delta and atomically advance its manifest.

    Segment files are content-addressed by checkpoint and payload hash. A crash
    before the manifest swap leaves only an ignored orphan; retrying the same
    checkpoint cannot corrupt the currently committed delta view.
    """
    path = Path(path)
    if checkpoint_index < 0:
        raise ValueError("checkpoint index must be non-negative")
    if (not isinstance(payload_metadata, dict) or collection_key in payload_metadata
            or not isinstance(records, list)):
        raise ValueError("delta metadata and records must be dictionary/list values")
    directory_name = path.name + ".delta"
    directory = path.parent / directory_name
    _assert_document_lease(directory, lease_required)
    directory.mkdir(parents=True, exist_ok=True)
    _assert_document_lease(directory, lease_required)

    manifest_file = delta_manifest_path(path)
    previous = _read_delta_manifest(path, collection_key) or {
        "schema_version": 1,
        "format": "jsonl-delta-v1",
        "logical_path": path.name,
        "collection_key": collection_key,
        "delta_directory": directory_name,
        "metadata": {},
        "segments": [],
    }
    if previous.get("delta_directory") != directory_name:
        raise ValueError("delta directory identity changed unexpectedly")

    segments = list(previous.get("segments", []))
    if records:
        chunks = []
        buffer = bytearray()
        for record in records:
            line = _compact_bytes(record) + bytes([10])
            if len(line) > MAX_FILE_BYTES:
                raise ValueError("one delta record exceeds the 50 MiB single-file limit")
            if buffer and len(buffer) + len(line) > SHARD_TARGET_BYTES:
                chunks.append(bytes(buffer))
                buffer = bytearray()
            buffer.extend(line)
        if buffer:
            chunks.append(bytes(buffer))

        replacements = []
        for part, raw in enumerate(chunks):
            digest = hashlib.sha256(raw).hexdigest()
            name = f"batch-{checkpoint_index:012d}-{part:03d}-{digest[:16]}.jsonl"
            segment_path = directory / name
            if not segment_path.exists():
                _atomic_write(segment_path, raw, lease_required=lease_required)
            elif hashlib.sha256(segment_path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"immutable delta segment collision: {segment_path}")
            replacements.append({
                "checkpoint_index": checkpoint_index,
                "file": name,
                "records": len(raw.splitlines()),
                "bytes": len(raw),
                "sha256": digest,
            })
        segments = [item for item in segments if int(item.get("checkpoint_index", -1)) != checkpoint_index]
        segments.extend(replacements)
        segments.sort(key=lambda item: (int(item.get("checkpoint_index", -1)), item.get("file", "")))

    manifest = dict(previous)
    manifest["metadata"] = dict(payload_metadata)
    manifest["segments"] = segments
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8") + bytes([10])
    if len(manifest_bytes) > MAX_FILE_BYTES:
        raise ValueError("delta manifest exceeds the 50 MiB single-file limit")
    _atomic_write(manifest_file, manifest_bytes, lease_required=lease_required)
    return {
        "storage": "jsonl-delta-v1",
        "checkpoint_index": checkpoint_index,
        "records": len(records),
        "segments": len(segments),
        "bytes": sum(int(item.get("bytes", 0)) for item in segments),
    }


def clear_document_delta(path: Path, collection_key: str, *, lease_required: bool = True) -> None:
    """Remove the delta manifest first; orphaned immutable segments are harmless."""
    path = Path(path)
    manifest_file = delta_manifest_path(path)
    if not manifest_file.exists():
        return
    _assert_document_lease(manifest_file, lease_required)
    manifest = _read_delta_manifest(path, collection_key)
    manifest_file.unlink()
    if manifest:
        directory = path.parent / str(manifest["delta_directory"])
        if directory.exists():
            _assert_document_lease(directory, lease_required)
            shutil.rmtree(directory)
