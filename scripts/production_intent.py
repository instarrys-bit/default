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
    for relative in inputs:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative or any(char in relative for char in "*?[]"):
            raise ValueError(f"production input path must be a literal repository-relative path: {relative}")
    overlap = {
        relative for relative in inputs
        if any(fnmatch.fnmatchcase(relative, pattern) for pattern in non_inputs)
    }
    if overlap:
        raise ValueError("production inputs also match non-production patterns: " + ", ".join(sorted(overlap)))
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
        if path.is_symlink():
            raise ValueError(f"production input path is a symlink: {relative}")
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


def compute_output_fingerprint(root: Path) -> str:
    """Fingerprint the three published policy outputs independently of input state."""
    entries = {}
    for relative in ("rulesets/direct.list", "rulesets/proxy.list", "rulesets/reject.list"):
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"published ruleset output is missing or unsafe: {relative}")
        entries[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
           revision: str | None = None, now: datetime | None = None,
           refresh_after_seconds: int = 691200) -> dict:
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
    if active_fingerprints:
        return {**base, "decision": "WAIT_FOR_ACTIVE", "reason": "a different production input fingerprint already has an active task; let its stale-input guard and recovery path settle first"}
    last = parse_timestamp(last_success_at)
    age = None if last is None else max(0, int((now - last).total_seconds()))
    refresh_due = event == "schedule" and (last is None or age >= refresh_after_seconds)
    # A changed input must be reconciled even if this exact fingerprint succeeded
    # in the past: stateful archives and outputs may have moved on (A -> B -> A).
    if path_classification["status"] == "INPUT_CHANGED":
        generation = revision or "unversioned"
        return {
            **base, "decision": "INPUT_CHANGED",
            "reason": "a registered production input changed; prior success for the same fingerprint does not prove current state is reconciled",
            "should_produce": True,
            "idempotency_key": f"production:input:{current_fingerprint}:{generation}",
        }
    if current_fingerprint in successful_fingerprints:
        if refresh_due:
            generation = last_success_at or "bootstrap"
            return {**base, "decision": "SCHEDULE_DUE", "reason": "the configured refresh interval has elapsed", "should_produce": True, "age_seconds": age, "idempotency_key": f"production:schedule:{current_fingerprint}:{generation}"}
        return {**base, "decision": "ALREADY_SATISFIED", "reason": "this input fingerprint already has a verified successful result", "age_seconds": age}
    if current_fingerprint != last_success_fingerprint:
        return {**base, "decision": "INPUT_CHANGED", "reason": "current production input fingerprint differs from the last successful audit", "should_produce": True, "idempotency_key": f"production:input:{current_fingerprint}:{revision or 'unversioned'}"}
    if refresh_due:
        generation = last_success_at or "bootstrap"
        return {**base, "decision": "SCHEDULE_DUE", "reason": "the configured refresh interval has elapsed", "should_produce": True, "age_seconds": age, "idempotency_key": f"production:schedule:{current_fingerprint}:{generation}"}
    return {**base, "decision": "ALREADY_SATISFIED", "reason": "inputs are unchanged and the refresh interval is not due", "age_seconds": age}



def register_unclassified_paths(paths, ledger, event, revision, run_id, run_url, now=None):
    """Record unknown paths in the Watchdog inbox; never treat registration as approval."""
    if ledger.get("schema_version") != 1 or not isinstance(ledger.get("entries"), list):
        raise ValueError("unsupported Watchdog registration ledger")
    stamp = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entries = {item["path"]: item for item in ledger["entries"]}
    normalized = set()
    for raw in paths:
        if not isinstance(raw, str):
            raise ValueError("unregistered paths must be strings")
        path = raw.strip().removeprefix("./")
        if not path or path.startswith("/") or "\\\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
            raise ValueError("unsafe or invalid repository path: " + repr(raw))
        if any(ord(char) < 32 for char in path):
            raise ValueError("control characters are not allowed in repository paths")
        normalized.add(path)
    for path in sorted(normalized):
        item = entries.get(path)
        if item is None:
            item = {"path": path, "status": "PENDING_CLASSIFICATION",
                    "first_seen_at": stamp, "last_seen_at": stamp, "seen_count": 0}
            entries[path] = item
        item["last_seen_at"] = stamp
        item["seen_count"] += 1
        item["last_seen_event"] = event
        item["last_seen_revision"] = revision
        item["last_seen_run_id"] = str(run_id)
        item["last_seen_run_url"] = run_url
    ledger["entries"] = sorted(entries.values(), key=lambda item: item["path"])
    ledger["updated_at"] = stamp
    return ledger

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("automation/production_inputs.json"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--paths-json", default="[]")
    parser.add_argument("--event", required=True)
    parser.add_argument("--revision", default="")
    parser.add_argument("--last-success-fingerprint", default="")
    parser.add_argument("--last-success-at", default="")
    parser.add_argument("--active-fingerprints-json", default="[]")
    parser.add_argument("--successful-fingerprints-json", default="[]")
    parser.add_argument("--refresh-after-seconds", type=int, default=691200)
    parser.add_argument("--register-ledger", type=Path)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-url", default="")
    args = parser.parse_args()
    try:
        if args.register_ledger is not None:
            paths = json.loads(args.paths_json)
            if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
                raise ValueError("paths-json must be a JSON string array")
            if not args.run_id or not args.run_url:
                raise ValueError("run-id and run-url are required for Watchdog registration")
            if args.register_ledger.exists():
                ledger = json.loads(args.register_ledger.read_text(encoding="utf-8"))
            else:
                ledger = {"schema_version": 1, "purpose": "Watchdog inbox for unregistered repository paths; registration is not approval.", "entries": []}
            ledger = register_unclassified_paths(
                paths, ledger, args.event, args.revision, args.run_id, args.run_url
            )
            args.register_ledger.parent.mkdir(parents=True, exist_ok=True)
            args.register_ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
            print(json.dumps({
                "registered_count": len(set(paths)),
                "pending_count": sum(item.get("status") == "PENDING_CLASSIFICATION" for item in ledger["entries"]),
                "paths": sorted(set(paths)),
            }, ensure_ascii=False))
            return 0
        if isinstance(args.refresh_after_seconds, bool) or args.refresh_after_seconds < 1:
            raise ValueError("refresh-after-seconds must be a positive integer")
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
            revision=args.revision or None,
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
