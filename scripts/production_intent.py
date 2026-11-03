#!/usr/bin/env python3
"""Deterministic production-demand classification and input fingerprinting."""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def load_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("unsupported production input manifest schema")
    inputs = value.get("production_input_paths")
    non_inputs = value.get("non_production_path_patterns")
    if not isinstance(inputs, list) or not inputs or any(not isinstance(x, str) or not x for x in inputs):
        raise ValueError("production_input_paths must be a non-empty string array")
    if len(inputs) != len(set(inputs)):
        raise ValueError("production input paths must be unique")
    if not isinstance(non_inputs, list) or any(not isinstance(x, str) or not x for x in non_inputs):
        raise ValueError("non_production_path_patterns must be a string array")
    overlap = set(inputs).intersection(non_inputs)
    if overlap:
        raise ValueError("a path cannot be both a production input and non-production path")
    return value


def classify_paths(paths: Iterable[str], manifest: dict) -> dict:
    inputs = set(manifest["production_input_paths"])
    patterns = manifest["non_production_path_patterns"]
    input_paths, non_input_paths, unknown_paths = [], [], []
    for raw in sorted(set(paths)):
        path = raw.strip().removeprefix("./")
        if not path:
            continue
        if path in inputs:
            input_paths.append(path)
        elif any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
            non_input_paths.append(path)
        else:
            unknown_paths.append(path)
    if unknown_paths:
        status = "REVIEW_REQUIRED"
    elif input_paths:
        status = "INPUT_CHANGED"
    else:
        status = "NO_INPUT_CHANGE"
    return {
        "status": status,
        "production_input_changes": input_paths,
        "non_production_changes": non_input_paths,
        "unknown_changes": unknown_paths,
    }


def compute_fingerprint(root: Path, manifest: dict) -> str:
    entries = {}
    for relative in sorted(manifest["production_input_paths"]):
        path = root / relative
        if not path.is_file():
            entries[relative] = "MISSING"
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries[relative] = digest
    payload = json.dumps(
        {"manifest_schema_version": manifest["schema_version"], "inputs": entries},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("last_success_at must include a timezone")
    return stamp.astimezone(timezone.utc)


def decide(*, event: str, current_fingerprint: str, last_success_fingerprint: str | None,
           path_classification: dict, last_success_at: str | None,
           active_fingerprints: set[str] | None = None,
           successful_fingerprints: set[str] | None = None,
           now: datetime | None = None, refresh_after_seconds: int = 691200) -> dict:
    now = now or datetime.now(timezone.utc)
    active_fingerprints = active_fingerprints or set()
    successful_fingerprints = successful_fingerprints or set()
    base = {
        "fingerprint": current_fingerprint,
        "event": event,
        "reason": "",
        "should_produce": False,
    }
    if event in {"repository_dispatch", "workflow_run"}:
        return {**base, "decision": "OBSERVE_ONLY", "reason": "supervision events cannot create production demand"}
    if event not in {"push", "schedule", "workflow_dispatch"}:
        return {**base, "decision": "REVIEW_REQUIRED", "reason": "event type is not authorized to request production"}
    if path_classification["status"] == "REVIEW_REQUIRED":
        return {**base, "decision": "REVIEW_REQUIRED", "reason": "changed paths include unregistered files"}
    if current_fingerprint in active_fingerprints:
        return {**base, "decision": "IN_PROGRESS", "reason": "the same input fingerprint already has an active task"}
    if current_fingerprint != last_success_fingerprint:
        return {**base, "decision": "INPUT_CHANGED", "reason": "current production input fingerprint differs from the last successful audit", "should_produce": True}
    if current_fingerprint in successful_fingerprints and event != "schedule":
        return {**base, "decision": "ALREADY_SATISFIED", "reason": "the current input fingerprint already has a verified successful result"}
    last = parse_timestamp(last_success_at)
    age = None if last is None else max(0, int((now - last).total_seconds()))
    if event == "schedule" and (last is None or age >= refresh_after_seconds):
        return {**base, "decision": "SCHEDULE_DUE", "reason": "the configured refresh interval has elapsed", "should_produce": True, "age_seconds": age}
    return {**base, "decision": "ALREADY_SATISFIED", "reason": "inputs are unchanged and the refresh interval is not due", "age_seconds": age}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("automation/production_inputs.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--paths-json", default="[]")
    parser.add_argument("--event", required=True)
    parser.add_argument("--last-success-fingerprint", default="")
    parser.add_argument("--last-success-at", default="")
    parser.add_argument("--active-fingerprints-json", default="[]")
    parser.add_argument("--successful-fingerprints-json", default="[]")
    parser.add_argument("--refresh-after-seconds", type=int, default=691200)
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        paths = json.loads(args.paths_json)
        active = set(json.loads(args.active_fingerprints_json))
        successful = set(json.loads(args.successful_fingerprints_json))
        if not isinstance(paths, list) or any(not isinstance(x, str) for x in paths):
            raise ValueError("paths-json must be a JSON string array")
        fingerprint = compute_fingerprint(args.root, manifest)
        classification = classify_paths(paths, manifest)
        result = decide(
            event=args.event, current_fingerprint=fingerprint,
            last_success_fingerprint=args.last_success_fingerprint or None,
            path_classification=classification, last_success_at=args.last_success_at or None,
            active_fingerprints=active, successful_fingerprints=successful,
            refresh_after_seconds=args.refresh_after_seconds,
        )
        result["path_classification"] = classification
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PRODUCTION INTENT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
