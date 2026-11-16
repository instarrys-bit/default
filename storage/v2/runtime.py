#!/usr/bin/env python3
"""V2 event-sourced Storage Management core.

The GitHub Contents API document is the durable CAS boundary. Projections are
rebuildable from the hash-chained event list and are never authoritative.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import secrets
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = "storage/v2/state.json"
MAX_STATE_BYTES = 45_000_000
EVENT_TYPES = {
    "TASK_ENQUEUED", "TASK_CLAIMED", "TASK_STARTED", "TASK_SUCCEEDED",
    "TASK_FAILED", "TASK_REQUEUED", "TASK_DEAD_LETTER", "TASK_CANCELLED",
    "RESOURCE_ACQUIRED", "RESOURCE_RELEASED",
}
TASK_TRANSITIONS = {
    "QUEUED": {"CLAIMED", "CANCELLED"},
    "CLAIMED": {"RUNNING", "QUEUED", "FAILED", "DEAD_LETTER", "CANCELLED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "QUEUED", "DEAD_LETTER"},
    "FAILED": {"QUEUED", "DEAD_LETTER"},
    "SUCCEEDED": set(), "DEAD_LETTER": set(), "CANCELLED": set(),
}


class StorageError(RuntimeError):
    pass


class Conflict(StorageError):
    pass


class NotInitialized(StorageError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def empty_state(epoch_id: str) -> dict:
    if not isinstance(epoch_id, str) or not epoch_id.strip() or len(epoch_id) > 120:
        raise ValueError("epoch_id must be a non-empty string of at most 120 characters")
    return {
        "schema_version": 1,
        "epoch_id": epoch_id,
        "revision": 0,
        "events": [],
        "created_at": utc_now(),
    }


def validate_state(state: object) -> dict:
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("unsupported storage state schema")
    if not isinstance(state.get("epoch_id"), str) or not state["epoch_id"]:
        raise ValueError("storage state epoch_id is required")
    revision = state.get("revision")
    events = state.get("events")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ValueError("storage state revision must be a non-negative integer")
    if not isinstance(events, list) or len(events) != revision:
        raise ValueError("revision must equal the append-only event count")
    previous = "0" * 64
    seen_idem = {}
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        body = {k: v for k, v in event.items() if k != "event_sha256"}
        digest = sha256(canonical_bytes(body))
        if event.get("sequence") != index or event.get("previous_event_sha256") != previous:
            raise ValueError("event sequence or hash-chain predecessor mismatch")
        if event.get("event_sha256") != digest:
            raise ValueError("event hash mismatch")
        idem = event.get("idempotency_key")
        if not isinstance(idem, str) or not idem:
            raise ValueError("event idempotency_key is required")
        if idem in seen_idem and seen_idem[idem] != digest:
            raise ValueError("idempotency key reused for a different event")
        seen_idem[idem] = digest
        previous = digest
    return state


def project(state: dict) -> dict:
    validate_state(state)
    tasks: dict[str, dict] = {}
    resources: dict[str, dict] = {}
    for event in state["events"]:
        kind = event["event_type"]
        payload = event["payload"]
        if kind == "TASK_ENQUEUED":
            task_id = payload["task_id"]
            if task_id in tasks:
                raise ValueError("duplicate task enqueue")
            tasks[task_id] = {
                "task_id": task_id, "status": "QUEUED", "attempts": 0,
                "max_attempts": payload["max_attempts"],
                "input_artifact_ids": payload.get("input_artifact_ids", []),
                "created_at": event["created_at"], "last_event": event["event_sha256"],
                "task_lease": None,
            }
        elif kind.startswith("TASK_"):
            task_id = payload["task_id"]
            if task_id not in tasks:
                raise ValueError("task event references an unknown task")
            task = tasks[task_id]
            target = kind.removeprefix("TASK_")
            target = {"STARTED": "RUNNING", "REQUEUED": "QUEUED"}.get(target, target)
            if target not in TASK_TRANSITIONS[task["status"]]:
                raise ValueError(f"invalid task transition: {task['status']} -> {target}")
            if kind == "TASK_CLAIMED":
                task["attempts"] += 1
                task["task_lease"] = {
                    "lease_id": payload["lease_id"], "owner": payload["owner"],
                    "token": payload["token"], "expires_at": payload["expires_at"],
                    "status": "ACTIVE",
                }
            if kind in {"TASK_REQUEUED", "TASK_FAILED", "TASK_SUCCEEDED", "TASK_DEAD_LETTER", "TASK_CANCELLED"}:
                if task.get("task_lease"):
                    task["task_lease"]["status"] = "RELEASED"
            if kind == "TASK_FAILED":
                task["last_error"] = payload.get("error")
            if kind == "TASK_SUCCEEDED":
                task["result_artifact_id"] = payload["result_artifact_id"]
            task["status"] = target
            task["last_event"] = event["event_sha256"]
        elif kind == "RESOURCE_ACQUIRED":
            key = payload["resource_key"]
            old = resources.get(key)
            if old and old["status"] == "ACTIVE":
                raise ValueError("resource already has an active lease")
            expected = (old["fencing_token"] + 1) if old else 1
            if payload["fencing_token"] != expected:
                raise ValueError("resource fencing token must increase monotonically")
            resources[key] = {
                "status": "ACTIVE", "lease_id": payload["lease_id"],
                "task_id": payload["task_id"], "owner": payload["owner"],
                "fencing_token": payload["fencing_token"],
                "expires_at": payload["expires_at"], "last_event": event["event_sha256"],
            }
        elif kind == "RESOURCE_RELEASED":
            key = payload["resource_key"]
            old = resources.get(key)
            if not old or old["status"] != "ACTIVE":
                raise ValueError("cannot release a resource without an active lease")
            if old["lease_id"] != payload["lease_id"] or old["fencing_token"] != payload["fencing_token"]:
                raise Conflict("resource lease or fencing token mismatch")
            old["status"] = "RELEASED"
            old["last_event"] = event["event_sha256"]
    return {
        "epoch_id": state["epoch_id"], "revision": state["revision"],
        "task_count": len(tasks), "tasks": tasks,
        "resource_leases": resources,
        "status_counts": _status_counts(tasks),
    }


def _status_counts(tasks: dict) -> dict:
    counts: dict[str, int] = {}
    for task in tasks.values():
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    return counts


def append_event(state: dict, *, event_type: str, payload: dict, actor: str,
                 idempotency_key: str, expected_revision: int, created_at: str | None = None) -> tuple[dict, dict]:
    validate_state(state)
    if event_type not in EVENT_TYPES:
        raise ValueError("unsupported event_type")
    if not isinstance(payload, dict) or not isinstance(actor, str) or not actor.strip():
        raise ValueError("payload and actor are required")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must contain 1..200 characters")
    # Resolve retries before checking the caller's expected revision. A caller
    # may have lost the first response after the event was durably committed.
    for old in state["events"]:
        if old["idempotency_key"] == idempotency_key:
            same_request = (
                old["event_type"] == event_type
                and old["payload"] == payload
                and old["actor"] == actor
            )
            if same_request:
                return copy.deepcopy(state), {"created": False, "event": old}
            raise Conflict("idempotency key already used for a different event")
    if expected_revision != state["revision"]:
        raise Conflict(f"revision conflict: expected {expected_revision}, current {state['revision']}")
    body = {
        "sequence": state["revision"] + 1,
        "event_type": event_type,
        "payload": copy.deepcopy(payload),
        "actor": actor,
        "idempotency_key": idempotency_key,
        "created_at": created_at or utc_now(),
        "previous_event_sha256": state["events"][-1]["event_sha256"] if state["events"] else "0" * 64,
    }
    digest = sha256(canonical_bytes(body))
    event = {**body, "event_sha256": digest}
    candidate = copy.deepcopy(state)
    candidate["events"].append(event)
    candidate["revision"] += 1
    project(candidate)
    return candidate, {"created": True, "event": event}


class GitHubContentsBackend:
    """Single-document GitHub Contents API CAS backend; one commit per event."""
    def __init__(self, repository: str, branch: str, token: str, path: str = STATE_PATH, timeout: int = 20):
        if not repository or "/" not in repository or not branch or not token:
            raise ValueError("repository, branch and token are required")
        self.repository, self.branch, self.token, self.path, self.timeout = repository, branch, token, path, timeout
        self.endpoint = f"https://api.github.com/repos/{repository}/contents/{urllib.parse.quote(path, safe='/')}"

    def _request(self, method: str, url: str, payload: dict | None = None):
        headers = {
            "Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "shadowrocket-v2-storage",
        }
        data = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in {409, 422}:
                raise Conflict(f"GitHub CAS conflict ({exc.code})") from None
            if exc.code == 404:
                return None
            raise StorageError(f"GitHub API HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise StorageError(f"GitHub API request failed: {exc}") from None
        return json.loads(raw.decode("utf-8")) if raw else None

    def read(self) -> tuple[dict | None, str | None]:
        result = self._request("GET", self.endpoint + "?" + urllib.parse.urlencode({"ref": self.branch}))
        if result is None:
            return None, None
        raw = base64.b64decode(result["content"], validate=False)
        if len(raw) > MAX_STATE_BYTES:
            raise StorageError("state document exceeds the 45 MB safety limit")
        state = validate_state(json.loads(raw.decode("utf-8")))
        return state, result["sha"]

    def compare_and_swap(self, candidate: dict, *, expected_revision: int, expected_blob_sha: str | None, message: str) -> str:
        current, blob_sha = self.read()
        current_revision = current["revision"] if current else -1
        if current_revision != expected_revision or blob_sha != expected_blob_sha:
            raise Conflict("storage state compare-and-swap failed")
        if candidate.get("revision") != expected_revision + 1:
            raise ValueError("candidate revision must advance exactly once")
        raw = (json.dumps(candidate, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        if len(raw) > MAX_STATE_BYTES:
            raise StorageError("state document exceeds the 45 MB safety limit; shard migration required")
        payload = {
            "message": message, "content": base64.b64encode(raw).decode("ascii"),
            "branch": self.branch,
        }
        if blob_sha:
            payload["sha"] = blob_sha
        result = self._request("PUT", self.endpoint, payload)
        if not result:
            raise StorageError("GitHub write returned no result")
        new_blob_sha = (result.get("content") or {}).get("sha")
        verified, verified_sha = self.read()
        if verified is None or verified["revision"] != candidate["revision"] or verified_sha != new_blob_sha:
            raise StorageError("independent read-back verification failed")
        return new_blob_sha


def assert_automation_write_allowed(path: str, actor: str) -> None:
    """Default-deny path policy for automated identities; human edits are separate."""
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError("unsafe repository path")
    if actor == "human_user":
        return
    if normalized == "modules/uu.conf" or normalized.startswith("modules/"):
        raise PermissionError("automated workflows cannot write modules or modules/uu.conf")
    allowed = {
        "storage/v2/state.json", "storage/v2/queue_seed.json",
        "storage/v2/production_write_policy.json",
        "rulesets/direct.list", "rulesets/proxy.list", "rulesets/reject.list",
        "rulesets/manifest.json", "rulesets/lifecycle_state.json",
        "rulesets/lifecycle_observations.json", "automation/release_manifest.json",
    }
    if normalized not in allowed and not normalized.startswith("storage/v2/artifacts/"):
        raise PermissionError(f"automated write path is not allowlisted: {normalized}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "main"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--epoch-id", required=True)
    init.add_argument("--approved-seed-sha", required=True)
    read = sub.add_parser("read")
    append = sub.add_parser("append")
    append.add_argument("--event-type", required=True, choices=sorted(EVENT_TYPES))
    append.add_argument("--payload", required=True)
    append.add_argument("--actor", required=True)
    append.add_argument("--idempotency-key", required=True)
    append.add_argument("--expected-revision", required=True, type=int)
    args = parser.parse_args()
    backend = GitHubContentsBackend(args.repository, args.branch, args.token)
    try:
        if args.command == "init":
            seed_path = Path(__file__).with_name("queue_seed.json")
            seed = json.loads(seed_path.read_text(encoding="utf-8"))
            actual_seed_sha = sha256(canonical_bytes(seed))
            if not secrets.compare_digest(actual_seed_sha, args.approved_seed_sha):
                raise ValueError("approved seed SHA does not match checked-in V2 seed")
            current, _ = backend.read()
            if current is not None:
                raise Conflict("V2 storage is already initialized")
            candidate = empty_state(args.epoch_id)
            backend.compare_and_swap(candidate, expected_revision=-1, expected_blob_sha=None, message="chore(v2): initialize storage epoch")
            print(json.dumps({"initialized": True, "epoch_id": args.epoch_id, "seed_sha256": actual_seed_sha}))
        elif args.command == "read":
            state, blob_sha = backend.read()
            if state is None:
                raise NotInitialized("V2 storage has not been initialized")
            print(json.dumps({"state": state, "projection": project(state), "blob_sha": blob_sha}, ensure_ascii=False))
        else:
            state, blob_sha = backend.read()
            if state is None:
                raise NotInitialized("V2 storage has not been initialized")
            candidate, result = append_event(
                state, event_type=args.event_type, payload=json.loads(args.payload),
                actor=args.actor, idempotency_key=args.idempotency_key,
                expected_revision=args.expected_revision,
            )
            if result["created"]:
                backend.compare_and_swap(candidate, expected_revision=state["revision"], expected_blob_sha=blob_sha, message=f"chore(v2): append {args.event_type}")
            print(json.dumps(result, ensure_ascii=False))
    except (StorageError, ValueError, OSError, PermissionError) as exc:
        print(f"storage-v2: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
