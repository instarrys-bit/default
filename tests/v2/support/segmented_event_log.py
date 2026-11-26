"""Pure serialization and integrity checks for the V2 append-only event log."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Mapping

from runtime import canonical_bytes, sha256, validate_state

MAX_SEGMENT_BYTES = 40_000_000
SEGMENT_ROOT = "storage/v2/state/segments"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _event_line(event: dict) -> bytes:
    return canonical_bytes(event) + b"\n"


def _segment_record(index: int, raw: bytes) -> dict:
    events = [json.loads(line.decode("utf-8")) for line in raw.splitlines()]
    return {
        "index": index,
        "path": f"{SEGMENT_ROOT}/segment-{index:08d}.jsonl",
        "first_sequence": events[0]["sequence"],
        "last_sequence": events[-1]["sequence"],
        "record_count": len(events),
        "byte_count": len(raw),
        "sha256": sha256(raw),
    }


def _make_manifest(state: dict, payloads: Mapping[str, bytes], *, max_segment_bytes: int) -> dict:
    records = []
    for index in range(1, len(payloads) + 1):
        path = f"{SEGMENT_ROOT}/segment-{index:08d}.jsonl"
        raw = payloads[path]
        if not raw or len(raw) > max_segment_bytes:
            raise ValueError("segment is empty or exceeds the configured byte limit")
        records.append(_segment_record(index, raw))
    unsigned = {
        "schema_version": 1,
        "epoch_id": state["epoch_id"],
        "revision": state["revision"],
        "total_event_count": len(state["events"]),
        "segment_count": len(records),
        "last_event_sha256": state["events"][-1]["event_sha256"] if state["events"] else "0" * 64,
        "created_at": state["created_at"],
        "updated_at": _now(),
        "segments": records,
    }
    manifest = copy.deepcopy(unsigned)
    manifest["manifest_sha256"] = sha256(canonical_bytes(unsigned))
    return manifest


def build_segmented_state(state: dict, *, max_segment_bytes: int = MAX_SEGMENT_BYTES) -> tuple[dict, dict[str, bytes]]:
    """Serialize a validated event state into bounded, ordered JSONL segments."""
    validate_state(state)
    if isinstance(max_segment_bytes, bool) or not isinstance(max_segment_bytes, int) or max_segment_bytes < 128:
        raise ValueError("max_segment_bytes must be an integer of at least 128")
    payloads: dict[str, bytes] = {}
    current = bytearray()
    index = 1
    for event in state["events"]:
        line = _event_line(event)
        if len(line) > max_segment_bytes:
            raise ValueError("a single event exceeds the segment byte limit")
        if current and len(current) + len(line) > max_segment_bytes:
            payloads[f"{SEGMENT_ROOT}/segment-{index:08d}.jsonl"] = bytes(current)
            index += 1
            current = bytearray()
        current.extend(line)
    if current:
        payloads[f"{SEGMENT_ROOT}/segment-{index:08d}.jsonl"] = bytes(current)
    return _make_manifest(state, payloads, max_segment_bytes=max_segment_bytes), payloads


def verify_segmented_state(
    manifest: dict,
    payloads: Mapping[str, bytes],
    *,
    max_segment_bytes: int = MAX_SEGMENT_BYTES,
) -> dict:
    """Verify manifest digest, all segment digests/counts/order, and event hash chain."""
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported segmented event manifest schema")
    unsigned = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    supplied = manifest.get("manifest_sha256")
    if not isinstance(supplied, str) or supplied != sha256(canonical_bytes(unsigned)):
        raise ValueError("manifest SHA-256 mismatch")
    records = manifest.get("segments")
    if not isinstance(records, list) or manifest.get("segment_count") != len(records):
        raise ValueError("manifest segment count mismatch")
    expected_paths = {f"{SEGMENT_ROOT}/segment-{i:08d}.jsonl" for i in range(1, len(records) + 1)}
    if set(payloads) != expected_paths:
        raise ValueError("segment payload set does not match the manifest")
    events = []
    expected_sequence = 1
    for index, record in enumerate(records, start=1):
        path = f"{SEGMENT_ROOT}/segment-{index:08d}.jsonl"
        if not isinstance(record, dict) or record.get("index") != index or record.get("path") != path:
            raise ValueError("manifest segment order or path is invalid")
        raw = payloads[path]
        if not isinstance(raw, bytes) or not raw or len(raw) > max_segment_bytes:
            raise ValueError("segment is empty or exceeds the configured byte limit")
        if record.get("byte_count") != len(raw) or record.get("sha256") != sha256(raw):
            raise ValueError("segment byte count or SHA-256 mismatch")
        lines = raw.splitlines()
        if len(lines) != record.get("record_count"):
            raise ValueError("segment record count mismatch")
        decoded = []
        for line in lines:
            try:
                event = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("segment contains invalid JSONL") from exc
            if not isinstance(event, dict) or event.get("sequence") != expected_sequence:
                raise ValueError("event sequence is discontinuous")
            decoded.append(event)
            events.append(event)
            expected_sequence += 1
        if (record.get("first_sequence") != decoded[0]["sequence"]
                or record.get("last_sequence") != decoded[-1]["sequence"]):
            raise ValueError("segment sequence range mismatch")
    if manifest.get("revision") != len(events) or manifest.get("total_event_count") != len(events):
        raise ValueError("manifest aggregate event count mismatch")
    last_hash = events[-1]["event_sha256"] if events else "0" * 64
    if manifest.get("last_event_sha256") != last_hash:
        raise ValueError("manifest terminal event hash mismatch")
    state = {
        "schema_version": 1,
        "epoch_id": manifest.get("epoch_id"),
        "revision": len(events),
        "events": events,
        "created_at": manifest.get("created_at"),
    }
    return validate_state(state)


def append_segmented_event(
    manifest: dict,
    payloads: Mapping[str, bytes],
    event_state: dict,
    *,
    max_segment_bytes: int = MAX_SEGMENT_BYTES,
) -> tuple[dict, dict[str, bytes]]:
    """Append exactly one already-hash-chained event, retaining all prior history."""
    current = verify_segmented_state(manifest, payloads, max_segment_bytes=max_segment_bytes)
    validate_state(event_state)
    if event_state["epoch_id"] != current["epoch_id"]:
        raise ValueError("event state epoch does not match the current manifest")
    if event_state["revision"] != current["revision"] + 1:
        raise ValueError("event state revision must advance exactly once")
    if event_state["events"][:-1] != current["events"]:
        raise ValueError("event state must preserve the complete previous event prefix")
    updated = dict(payloads)
    line = _event_line(event_state["events"][-1])
    if len(line) > max_segment_bytes:
        raise ValueError("a single event exceeds the segment byte limit")
    if updated:
        last_path = f"{SEGMENT_ROOT}/segment-{len(updated):08d}.jsonl"
        tail = updated[last_path]
        if len(tail) + len(line) <= max_segment_bytes:
            updated[last_path] = tail + line
        else:
            next_path = f"{SEGMENT_ROOT}/segment-{len(updated) + 1:08d}.jsonl"
            updated[next_path] = line
    else:
        updated[f"{SEGMENT_ROOT}/segment-{1:08d}.jsonl"] = line
    new_manifest = _make_manifest(event_state, updated, max_segment_bytes=max_segment_bytes)
    verify_segmented_state(new_manifest, updated, max_segment_bytes=max_segment_bytes)
    return new_manifest, updated
