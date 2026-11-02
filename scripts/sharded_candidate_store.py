#!/usr/bin/env python3
"""GitHub-repository-backed, sharded candidate storage primitives.

The module deliberately uses only the Python standard library. Candidate records
are immutable gzip-compressed NDJSON shards; a small JSON manifest is the index.
It does not delete or rewrite legacy JSON inputs.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Iterable, Iterator, Any

SCHEMA_VERSION = 1
MAX_CANDIDATES = 30_000_000
DEFAULT_SHARD_RECORDS = 50_000
DEFAULT_MAX_SHARD_BYTES = 48 * 1024 * 1024
MANIFEST_NAME = "manifest.json"


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(root: Path) -> dict:
    path = root / MANIFEST_NAME
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "max_candidates": MAX_CANDIDATES,
                "candidate_count": 0, "shard_count": 0, "shards": []}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported candidate-store manifest schema")
    count = manifest.get("candidate_count")
    if not isinstance(count, int) or count < 0 or count > MAX_CANDIDATES:
        raise ValueError("candidate-store manifest count is outside the hard limit")
    shards = manifest.get("shards")
    if not isinstance(shards, list):
        raise ValueError("candidate-store manifest shards must be a list")
    total = 0
    paths = set()
    for shard in shards:
        if not isinstance(shard, dict):
            raise ValueError("candidate-store shard entry must be an object")
        relative = shard.get("path")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("candidate-store shard path is unsafe")
        if relative in paths:
            raise ValueError("duplicate candidate-store shard path")
        paths.add(relative)
        records = shard.get("record_count")
        digest = shard.get("sha256")
        if not isinstance(records, int) or records < 0:
            raise ValueError("candidate-store shard record_count is invalid")
        if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError("candidate-store shard checksum is invalid")
        total += records
    if total != count or manifest.get("shard_count") != len(shards):
        raise ValueError("candidate-store manifest record/shard count mismatch")
    return manifest


def iter_shard(path: Path) -> Iterator[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: candidate record must be a JSON object")
            yield value


def iter_records(root: Path, manifest: dict | None = None) -> Iterator[dict]:
    manifest = manifest or load_manifest(root)
    for shard in manifest["shards"]:
        path = root / shard["path"]
        if not path.is_file():
            raise FileNotFoundError(f"candidate shard missing: {path}")
        if sha256_file(path) != shard["sha256"]:
            raise ValueError(f"candidate shard checksum mismatch: {path}")
        seen = 0
        for record in iter_shard(path):
            seen += 1
            yield record
        if seen != shard["record_count"]:
            raise ValueError(f"candidate shard record count mismatch: {path}")


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def append_records(root: Path, records: Iterable[dict], *, shard_records: int = DEFAULT_SHARD_RECORDS,
                   max_candidates: int = MAX_CANDIDATES) -> dict:
    """Append immutable shards. Duplicate identity is SHA-256 of canonical record bytes.

    A disk-backed SQLite index is rebuilt from existing shards on each invocation,
    avoiding a 30-million-entry in-memory set. The index is temporary runner state.
    """
    if shard_records < 1 or max_candidates < 1 or max_candidates > MAX_CANDIDATES:
        raise ValueError("invalid shard size or candidate cap")
    root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(root)
    current = int(manifest["candidate_count"])
    if current > max_candidates:
        raise ValueError("existing candidate pool exceeds configured maximum")

    with tempfile.TemporaryDirectory(prefix="candidate-index-") as temp:
        db = sqlite3.connect(str(Path(temp) / "index.sqlite3"))
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("CREATE TABLE seen (digest TEXT PRIMARY KEY)")
        for record in iter_records(root, manifest):
            db.execute("INSERT OR IGNORE INTO seen VALUES (?)",
                       (hashlib.sha256(canonical_json(record)).hexdigest(),))
        db.commit()

        new_shards = []
        batch = []
        accepted = 0

        def flush_batch(items: list[dict]) -> None:
            nonlocal accepted
            if not items:
                return
            index = len(manifest["shards"]) + len(new_shards)
            relative = f"shards/part-{index:06d}.ndjson.gz"
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
            count = 0
            try:
                with os.fdopen(fd, "wb") as raw:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                        for item in items:
                            compressed.write(canonical_json(item))
                            count += 1
                    raw.flush()
                    os.fsync(raw.fileno())
                os.replace(temp_name, target)
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            new_shards.append({"path": relative, "record_count": count, "sha256": sha256_file(target),
                               "compression": "gzip", "format": "ndjson"})
            accepted += count

        for record in records:
            if not isinstance(record, dict):
                raise ValueError("candidate record must be a JSON object")
            digest = hashlib.sha256(canonical_json(record)).hexdigest()
            inserted = db.execute("INSERT OR IGNORE INTO seen VALUES (?)", (digest,)).rowcount
            if not inserted:
                continue
            if current + accepted + len(batch) >= max_candidates:
                raise ValueError(f"candidate pool cap exceeded ({max_candidates:,}); refusing partial admission")
            batch.append(record)
            if len(batch) >= shard_records:
                flush_batch(batch)
                batch = []
        flush_batch(batch)
        db.close()

    updated = {
        "schema_version": SCHEMA_VERSION,
        "max_candidates": max_candidates,
        "candidate_count": current + accepted,
        "shard_count": len(manifest["shards"]) + len(new_shards),
        "deduplication": "sha256(canonical-json); disk-backed sqlite index rebuilt per run",
        "shards": manifest["shards"] + new_shards,
    }
    _atomic_json(root / MANIFEST_NAME, updated)
    return {"added": accepted, "total": updated["candidate_count"], "shards_added": len(new_shards)}


def verify_store(root: Path) -> dict:
    manifest = load_manifest(root)
    actual = 0
    for _ in iter_records(root, manifest):
        actual += 1
    if actual != manifest["candidate_count"]:
        raise ValueError("candidate-store total does not match manifest")
    return {"candidate_count": actual, "shard_count": len(manifest["shards"]), "verified": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--root", type=Path, required=True)
    ingest = sub.add_parser("ingest-ndjson")
    ingest.add_argument("--root", type=Path, required=True)
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--shard-records", type=int, default=DEFAULT_SHARD_RECORDS)
    ingest.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES)
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_store(args.root)
    else:
        def source() -> Iterator[dict]:
            with args.input.open("r", encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if line.strip():
                        value = json.loads(line)
                        if not isinstance(value, dict):
                            raise ValueError(f"input line {line_number}: expected JSON object")
                        yield value
        result = append_records(args.root, source(), shard_records=args.shard_records,
                                max_candidates=args.max_candidates)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
