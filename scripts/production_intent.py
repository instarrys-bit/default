#!/usr/bin/env python3
"""Deterministic production-demand classification and input fingerprinting."""
from __future__ import annotations


import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def load_manifest(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != 1:
        raise ValueError("unsupported production input manifest schema")
    inputs = value.get("production_input_paths")
    non_inputs = value.get("non_production_path_patterns")
    monitoring = value.get("monitoring_path_patterns", [])
    documentation = value.get("documentation_path_patterns", [])
    if not isinstance(inputs, list) or not inputs or any(not isinstance(x, str) or not x for x in inputs):
        raise ValueError("production_input_paths must be a non-empty string array")
    if len(inputs) != len(set(inputs)):
        raise ValueError("production input paths must be unique")
    if not isinstance(non_inputs, list) or any(not isinstance(x, str) or not x for x in non_inputs):
        raise ValueError("non_production_path_patterns must be a string array")
    for field, patterns in (("monitoring_path_patterns", monitoring), ("documentation_path_patterns", documentation)):
        if not isinstance(patterns, list) or any(not isinstance(x, str) or not x for x in patterns):
            raise ValueError(f"{field} must be a string array")
    for relative in inputs:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in relative or any(char in relative for char in "*?[]"):
            raise ValueError(f"production input path must be a literal repository-relative path: {relative}")
    all_non_inputs = non_inputs + monitoring + documentation
    overlap = {
        relative for relative in inputs
        if any(fnmatch.fnmatchcase(relative, pattern) for pattern in all_non_inputs)
    }
    if overlap:
        raise ValueError("production inputs also match non-production/monitoring/documentation patterns: " + ", ".join(sorted(overlap)))
    return value


def classify_paths(paths: Iterable[str], manifest: dict) -> dict:
    inputs = set(manifest["production_input_paths"])
    patterns = manifest["non_production_path_patterns"]
    monitoring_patterns = manifest.get("monitoring_path_patterns", [])
    documentation_patterns = manifest.get("documentation_path_patterns", [])
    input_paths, non_input_paths, monitoring_paths, documentation_paths, unknown_paths = [], [], [], [], []
    for raw in sorted(set(paths)):
        path = raw.strip().removeprefix("./")
        if not path:
            continue
        # Modules are an independent Shadowrocket deployment surface. The owner-
        # maintained uu.conf remains the sole module-path production input because
        # generated rulesets are checked against its routing policy; every other
        # module/script change must never create or block ruleset production.
        if path.startswith("modules/") and path != "modules/uu.conf":
            non_input_paths.append(path)
        elif path in inputs:
            input_paths.append(path)
        elif any(fnmatch.fnmatchcase(path, pattern) for pattern in documentation_patterns):
            documentation_paths.append(path)
        elif any(fnmatch.fnmatchcase(path, pattern) for pattern in monitoring_patterns):
            monitoring_paths.append(path)
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
        "monitoring_changes": monitoring_paths,
        "documentation_changes": documentation_paths,
        "unknown_changes": unknown_paths,
    }


def _fingerprint_input_bytes(relative: str, data: bytes) -> bytes:
    """Exclude only owner-baseline bookkeeping; the config blob remains a separate input."""
    if relative != "sources/policy.json":
        return data
    try:
        policy = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("sources/policy.json must be valid UTF-8 JSON for fingerprinting") from exc
    guard = policy.get("managed_config_guard") if isinstance(policy, dict) else None
    if isinstance(guard, dict):
        guard.pop("approved_git_blob_sha", None)
        guard.pop("last_user_approved_baseline_update", None)
    return json.dumps(
        policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_fingerprint(root: Path, manifest: dict) -> str:
    entries = {}
    for relative in sorted(manifest["production_input_paths"]):
        path = root / relative
        if path.is_symlink():
            raise ValueError(f"production input path is a symlink: {relative}")
        if not path.is_file():
            entries[relative] = "MISSING"
            continue
        data = path.read_bytes()
        if relative == "sources/request_domain_observations.json":
            seed = json.loads(data.decode("utf-8"))
            ledger = load_request_observation_ledger(root, seed)
            data = json.dumps(ledger, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(_fingerprint_input_bytes(relative, data)).hexdigest()
        entries[relative] = digest
    payload = json.dumps(
        {"manifest_schema_version": manifest["schema_version"], "inputs": entries},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


REQUEST_OBSERVATION_ISSUE_NUMBER = 317
REQUEST_OBSERVATION_MARKER = "<!-- shadowrocket-domain-observation:v1 -->"


def load_request_observation_ledger(root: Path, base_payload: dict | None = None,
                                    repository: str | None = None, token: str | None = None) -> dict:
    """Merge the read-only repository seed with append-only Issue #317 intake batches."""
    if base_payload is None:
        path = root / "sources/request_domain_observations.json"
        if path.is_file():
            base_payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            base_payload = {"schema_version": 1, "observations": []}
    if base_payload.get("schema_version") != 1 or not isinstance(base_payload.get("observations"), list):
        raise ValueError("unsupported request observation seed schema")
    repository = repository or os.environ.get("GITHUB_REPOSITORY", "")
    token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    if not repository or not token:
        return base_payload
    if "/" not in repository:
        raise ValueError("GITHUB_REPOSITORY must be owner/name to read external request observations")
    endpoint = f"https://api.github.com/repos/{repository}/issues/{REQUEST_OBSERVATION_ISSUE_NUMBER}/comments"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "shadowrocket-request-observation-reader",
    }
    merged = base_payload
    page = 1
    while True:
        url = endpoint + "?" + urlencode({"per_page": 100, "page": page})
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=15) as response:
                comments = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read external request observation ledger: {type(exc).__name__}") from None
        if not isinstance(comments, list):
            raise ValueError("external request observation comments must be an array")
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            body = comment.get("body")
            if not isinstance(body, str) or not body.startswith(REQUEST_OBSERVATION_MARKER + "\n"):
                continue
            try:
                batch = json.loads(body.split("\n", 1)[1])
            except json.JSONDecodeError as exc:
                raise ValueError("external request observation comment contains invalid JSON") from exc
            if (not isinstance(batch, dict) or batch.get("schema_version") != 1
                    or not isinstance(batch.get("run_id"), str) or not batch["run_id"]
                    or not isinstance(batch.get("domains"), list)):
                raise ValueError("external request observation batch has an invalid schema")
            merged = merge_request_observations(
                batch["domains"], merged, batch["run_id"],
                now=batch.get("observed_at") or comment.get("created_at"),
            )
        if len(comments) < 100:
            break
        page += 1
        if page > 100:
            raise ValueError("external request observation history exceeds the pagination safety limit")
    return merged


UNFINGERPRINTED_ACTIVE_PRODUCTION = "__unfingerprinted_active_production_task__"


def active_production_fingerprints(
    queue: dict, current_fingerprint: str, *, now: datetime | None = None
) -> list[str]:
    """Return only work that still owns a live production lease."""
    if not isinstance(queue, dict) or not isinstance(queue.get("tasks"), list):
        raise ValueError("task queue must contain a tasks array")
    if not isinstance(current_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", current_fingerprint):
        raise ValueError("current production fingerprint must be a SHA-256 hex digest")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(timezone.utc)
    active = set()
    for task in queue["tasks"]:
        if not isinstance(task, dict) or task.get("target_program_id") != "workflow_auto_sync":
            continue
        status = task.get("status")
        if status not in {"QUEUED", "CLAIMED", "VERIFYING"}:
            continue
        payload = task.get("input")
        fingerprint = payload.get("production_fingerprint") if isinstance(payload, dict) else None
        # A stale queued task has not acquired execution ownership. It must not
        # suppress a fresh task for current main; enqueue atomically supersedes it.
        if (status == "QUEUED" and fingerprint != current_fingerprint
                and not isinstance(task.get("dispatch_intent"), dict)):
            continue
        # CLAIMED/VERIFYING work is active only while its resource lease is live.
        # Once released or expired, fencing prevents that old worker from publishing.
        resource_lease = task.get("resource_lease")
        if status in {"CLAIMED", "VERIFYING"} and isinstance(resource_lease, dict):
            if resource_lease.get("status") == "RELEASED" or resource_lease.get("released_at"):
                continue
            expires_at = parse_timestamp(resource_lease.get("expires_at"))
            if expires_at is not None and expires_at <= now:
                continue
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            active.add(UNFINGERPRINTED_ACTIVE_PRODUCTION)
        else:
            active.add(fingerprint)
    return sorted(active)

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



def merge_request_observations(submitted, payload, run_id, now=None):
    """Merge one intake run into the latest observation ledger idempotently."""
    if payload.get("schema_version") != 1 or not isinstance(payload.get("observations"), list):
        raise ValueError("unsupported observation ledger schema")
    if not isinstance(submitted, list) or any(not isinstance(value, str) for value in submitted):
        raise ValueError("submitted hostnames must be a string array")
    if len(submitted) > 500:
        raise ValueError("maximum 500 hostnames per intake run")
    normalized = [value.strip().lower().rstrip(".") for value in submitted]
    pattern = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
    invalid = sorted({value for value in normalized if not pattern.fullmatch(value)})
    if invalid:
        raise ValueError("invalid hostname(s): " + ", ".join(invalid[:30]))
    run_key = str(run_id).strip()
    if not run_key:
        raise ValueError("intake run ID is required")
    stamp = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = {}
    for item in payload["observations"]:
        if not isinstance(item, dict) or not isinstance(item.get("domain"), str):
            raise ValueError("observation ledger contains an invalid row")
        domain = item["domain"].lower()
        if domain in rows:
            raise ValueError("observation ledger contains duplicate domains")
        rows[domain] = dict(item)
    counts = {}
    for domain in normalized:
        counts[domain] = counts.get(domain, 0) + 1
    for domain in sorted(counts):
        old = rows.get(domain, {})
        run_ids = old.get("observed_run_ids", [])
        if not isinstance(run_ids, list) or any(not isinstance(value, str) for value in run_ids):
            raise ValueError("observed_run_ids must be a string array")
        if run_key in run_ids:
            continue
        old["observations"] = int(old.get("observations", 0)) + counts[domain]
        run_ids.append(run_key)
        old["domain"] = domain
        old["observed_run_ids"] = run_ids
        old["first_seen"] = old.get("first_seen") or stamp
        old["last_seen"] = stamp
        old["intake"] = "github-workflow-dispatch"
        rows[domain] = old
    return {"schema_version": 1, "observations": [rows[key] for key in sorted(rows)]}


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
        if not path or path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
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
        observed_runs = item.get("observed_run_ids", [])
        if not isinstance(observed_runs, list) or any(not isinstance(value, str) for value in observed_runs):
            raise ValueError("observed_run_ids must be a string array")
        run_key = str(run_id)
        if run_key not in observed_runs:
            # Preserve compatibility with legacy entries whose last run predates
            # observed_run_ids, while making a retry idempotent after an intervening
            # concurrent run has updated last_seen_run_id.
            if item.get("last_seen_run_id") != run_key:
                item["seen_count"] += 1
            observed_runs.append(run_key)
        item["observed_run_ids"] = observed_runs
        item["last_seen_at"] = stamp
        item["last_seen_event"] = event
        item["last_seen_revision"] = revision
        item["last_seen_run_id"] = run_key
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
    parser.add_argument("--merge-observations", action="store_true")
    parser.add_argument("--observations-input", type=Path)
    parser.add_argument("--observation-ledger", type=Path, default=Path("sources/request_domain_observations.json"))
    parser.add_argument("--intake-run-id", default="")
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
        if args.merge_observations:
            if args.observations_input is None or not args.intake_run_id:
                raise ValueError("observations-input and intake-run-id are required for intake merge")
            submitted = json.loads(args.observations_input.read_text(encoding="utf-8"))
            if not isinstance(submitted, list):
                raise ValueError("observations input must be a JSON string array")
            if args.observation_ledger.exists():
                payload = json.loads(args.observation_ledger.read_text(encoding="utf-8"))
            else:
                payload = {"schema_version": 1, "observations": []}
            merged = merge_request_observations(submitted, payload, args.intake_run_id)
            args.observation_ledger.parent.mkdir(parents=True, exist_ok=True)
            args.observation_ledger.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
            print(json.dumps({"merged_domains": len(set(submitted)), "observation_count": len(merged["observations"])}, sort_keys=True))
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
