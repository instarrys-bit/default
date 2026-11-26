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
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_PATH = "storage/v2/state.json"
MAX_STATE_BYTES = 45_000_000
MAX_LEGACY_STATE_BYTES = 60_000_000
EVENT_TYPES = {
    "TASK_ENQUEUED", "TASK_CLAIMED", "TASK_STARTED", "TASK_SUCCEEDED",
    "TASK_FAILED", "TASK_REQUEUED", "TASK_DEAD_LETTER", "TASK_CANCELLED",
    "TASK_LEASE_RENEWED", "TASK_LEASE_EXPIRED",
    "RESOURCE_ACQUIRED", "RESOURCE_RELEASED",
    "RESOURCE_LEASE_RENEWED", "RESOURCE_LEASE_EXPIRED",
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


def _require_text(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"event payload {field} must be a non-empty string")
    return value


def _require_timestamp(value: object, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")


def _validate_resource_key(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ValueError("resource_key must be a canonical relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("resource_key contains an unsafe path segment")
    if value == "modules" or value.startswith("modules/"):
        raise ValueError("modules are not automation-writable resources")
    return value


def validate_event_payload(event_type: str, payload: dict) -> None:
    required = {
        "TASK_ENQUEUED": ("task_id",),
        "TASK_CLAIMED": ("task_id", "lease_id", "owner", "token", "expires_at"),
        "TASK_STARTED": ("task_id", "lease_id", "owner", "token"),
        "TASK_SUCCEEDED": ("task_id", "result_artifact_id", "lease_id", "owner", "token"),
        "TASK_FAILED": ("task_id", "error", "lease_id", "owner", "token"),
        "TASK_REQUEUED": ("task_id", "reason", "lease_id", "owner", "token"),
        "TASK_DEAD_LETTER": ("task_id", "reason"),
        "TASK_CANCELLED": ("task_id", "reason"),
        "TASK_LEASE_RENEWED": ("task_id", "lease_id", "owner", "token", "expires_at"),
        "TASK_LEASE_EXPIRED": ("task_id", "lease_id", "owner", "token"),
        "RESOURCE_ACQUIRED": ("resource_key", "lease_id", "task_id", "owner", "fencing_token", "expires_at"),
        "RESOURCE_RELEASED": ("resource_key", "lease_id", "fencing_token"),
        "RESOURCE_LEASE_RENEWED": ("resource_key", "lease_id", "task_id", "owner", "fencing_token", "expires_at"),
        "RESOURCE_LEASE_EXPIRED": ("resource_key", "lease_id", "fencing_token"),
    }[event_type]
    for field in required:
        if field not in payload:
            raise ValueError(f"{event_type} payload is missing {field}")
    if event_type == "TASK_ENQUEUED":
        _require_text(payload, "task_id")
        attempts = payload.get("max_attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 5:
            raise ValueError("max_attempts must be an integer from 1 to 5")
        artifact_ids = payload.get("input_artifact_ids", [])
        if not isinstance(artifact_ids, list) or any(not isinstance(x, str) or not x for x in artifact_ids):
            raise ValueError("input_artifact_ids must be an array of non-empty strings")
    elif event_type == "TASK_CLAIMED":
        for field in ("task_id", "lease_id", "owner", "token"):
            _require_text(payload, field)
        _require_timestamp(payload["expires_at"], "expires_at")
    elif event_type in {"TASK_STARTED", "TASK_SUCCEEDED", "TASK_FAILED", "TASK_REQUEUED", "TASK_DEAD_LETTER", "TASK_CANCELLED"}:
        _require_text(payload, "task_id")
        detail = {"TASK_SUCCEEDED": "result_artifact_id", "TASK_FAILED": "error"}.get(event_type)
        if detail:
            _require_text(payload, detail)
        if event_type in {"TASK_REQUEUED", "TASK_DEAD_LETTER", "TASK_CANCELLED"}:
            _require_text(payload, "reason")
        if event_type in {"TASK_STARTED", "TASK_SUCCEEDED", "TASK_FAILED", "TASK_REQUEUED"}:
            for field in ("lease_id", "owner", "token"):
                _require_text(payload, field)
    elif event_type in {"TASK_LEASE_RENEWED", "TASK_LEASE_EXPIRED"}:
        for field in ("task_id", "lease_id", "owner", "token"):
            _require_text(payload, field)
        if event_type == "TASK_LEASE_RENEWED":
            _require_timestamp(payload["expires_at"], "expires_at")
    elif event_type in {"RESOURCE_ACQUIRED", "RESOURCE_LEASE_RENEWED"}:
        _validate_resource_key(payload["resource_key"])
        for field in ("lease_id", "task_id", "owner"):
            _require_text(payload, field)
        token = payload["fencing_token"]
        if isinstance(token, bool) or not isinstance(token, int) or token < 1:
            raise ValueError("fencing_token must be a positive integer")
        _require_timestamp(payload["expires_at"], "expires_at")
    elif event_type in {"RESOURCE_RELEASED", "RESOURCE_LEASE_EXPIRED"}:
        _validate_resource_key(payload["resource_key"])
        _require_text(payload, "lease_id")
        token = payload["fencing_token"]
        if isinstance(token, bool) or not isinstance(token, int) or token < 1:
            raise ValueError("fencing_token must be a positive integer")


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
        _require_timestamp(event.get("created_at"), "event.created_at")
        event_type = event.get("event_type")
        payload = event.get("payload")
        if event_type not in EVENT_TYPES or not isinstance(payload, dict):
            raise ValueError("event type or payload is invalid")
        validate_event_payload(event_type, payload)
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
            if kind in {"TASK_LEASE_RENEWED", "TASK_LEASE_EXPIRED"}:
                lease = task.get("task_lease") or {}
                if (lease.get("status") != "ACTIVE"
                        or lease.get("lease_id") != payload["lease_id"]
                        or lease.get("owner") != payload["owner"]
                        or lease.get("token") != payload["token"]):
                    raise Conflict("task lease identity or token mismatch")
                now = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
                old_expiry = datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
                if kind == "TASK_LEASE_RENEWED":
                    new_expiry = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
                    if now >= old_expiry:
                        raise Conflict("an expired task lease cannot be renewed")
                    if new_expiry <= old_expiry:
                        raise ValueError("task lease renewal must extend expiry")
                    for resource in resources.values():
                        if (resource.get("status") == "ACTIVE"
                                and resource.get("task_id") == task_id
                                and datetime.fromisoformat(resource["expires_at"].replace("Z", "+00:00")) > new_expiry):
                            raise ValueError("task lease renewal cannot shorten below an active resource lease")
                    lease["expires_at"] = payload["expires_at"]
                else:
                    if now < old_expiry:
                        raise ValueError("task lease cannot be expired before its expiry timestamp")
                    lease["status"] = "EXPIRED"
                lease["last_event"] = event["event_sha256"]
                task["last_event"] = event["event_sha256"]
                continue
            if kind in {"TASK_STARTED", "TASK_SUCCEEDED", "TASK_FAILED"}:
                lease = task.get("task_lease") or {}
                if (lease.get("status") != "ACTIVE"
                        or lease.get("lease_id") != payload["lease_id"]
                        or lease.get("owner") != payload["owner"]
                        or lease.get("token") != payload["token"]):
                    raise Conflict("task operation lease identity or token mismatch")
                now = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
                expiry = datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
                if now >= expiry:
                    raise Conflict("task lease expired before worker operation was recorded")
            target = kind.removeprefix("TASK_")
            target = {"STARTED": "RUNNING", "REQUEUED": "QUEUED"}.get(target, target)
            if target not in TASK_TRANSITIONS[task["status"]]:
                raise ValueError(f"invalid task transition: {task['status']} -> {target}")
            if kind == "TASK_CLAIMED":
                if task["attempts"] >= task["max_attempts"]:
                    raise ValueError("task has exhausted its retry budget")
                if task.get("task_lease") and task["task_lease"].get("status") == "ACTIVE":
                    raise ValueError("task already has an active lease")
                task["attempts"] += 1
                task["task_lease"] = {
                    "lease_id": payload["lease_id"], "owner": payload["owner"],
                    "token": payload["token"], "expires_at": payload["expires_at"],
                    "status": "ACTIVE",
                }
            if kind == "TASK_STARTED" and (
                not task.get("task_lease") or task["task_lease"].get("status") != "ACTIVE"
            ):
                raise ValueError("TASK_STARTED requires an active task lease")
            if kind == "TASK_REQUEUED" and task["attempts"] >= task["max_attempts"]:
                raise ValueError("exhausted task must enter DEAD_LETTER, not QUEUED")
            if kind == "TASK_REQUEUED":
                lease = task.get("task_lease") or {}
                if (lease.get("status") not in {"EXPIRED", "RELEASED"}
                        or lease.get("lease_id") != payload["lease_id"]
                        or lease.get("owner") != payload["owner"]
                        or lease.get("token") != payload["token"]):
                    raise Conflict("task requeue requires the matching expired or released lease")
            if kind == "TASK_DEAD_LETTER" and task["status"] in {"CLAIMED", "RUNNING"}:
                lease_status = (task.get("task_lease") or {}).get("status")
                if lease_status not in {"EXPIRED", "RELEASED"}:
                    raise Conflict("active task lease must expire or be released before dead-lettering")
            if kind in {"TASK_REQUEUED", "TASK_FAILED", "TASK_SUCCEEDED", "TASK_DEAD_LETTER", "TASK_CANCELLED"}:
                active_resources = [
                    key for key, lease in resources.items()
                    if lease.get("status") == "ACTIVE" and lease.get("task_id") == task_id
                ]
                if active_resources:
                    raise ValueError("release task resource leases before task transition: " + ", ".join(active_resources))
                if task.get("task_lease"):
                    task["task_lease"]["status"] = "RELEASED"
            if kind == "TASK_FAILED":
                task["last_error"] = payload.get("error")
            if kind == "TASK_SUCCEEDED":
                task["result_artifact_id"] = payload["result_artifact_id"]
            task["status"] = target
            task["last_event"] = event["event_sha256"]
        elif kind in {"RESOURCE_LEASE_RENEWED", "RESOURCE_LEASE_EXPIRED"}:
            key = _validate_resource_key(payload["resource_key"])
            old = resources.get(key)
            if (not old or old.get("status") != "ACTIVE"
                    or old.get("lease_id") != payload["lease_id"]
                    or old.get("fencing_token") != payload["fencing_token"]):
                raise Conflict("resource lease or fencing token mismatch")
            now = datetime.fromisoformat(event["created_at"].replace("Z", "+00:00"))
            old_expiry = datetime.fromisoformat(old["expires_at"].replace("Z", "+00:00"))
            if kind == "RESOURCE_LEASE_RENEWED":
                task = tasks.get(payload["task_id"])
                if (not task or old.get("task_id") != payload["task_id"]
                        or old.get("owner") != payload["owner"]):
                    raise Conflict("resource lease task or owner mismatch")
                task_lease = task.get("task_lease") or {}
                if task_lease.get("status") != "ACTIVE" or task_lease.get("owner") != payload["owner"]:
                    raise Conflict("resource renewal requires the matching active task lease")
                new_expiry = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
                task_expiry = datetime.fromisoformat(task_lease["expires_at"].replace("Z", "+00:00"))
                if now >= old_expiry:
                    raise Conflict("an expired resource lease cannot be renewed")
                if new_expiry <= old_expiry:
                    raise ValueError("resource lease renewal must extend expiry")
                if new_expiry > task_expiry:
                    raise ValueError("resource lease cannot outlive its task lease")
                old["expires_at"] = payload["expires_at"]
            else:
                if now < old_expiry:
                    raise ValueError("resource lease cannot be expired before its expiry timestamp")
                old["status"] = "EXPIRED"
            old["last_event"] = event["event_sha256"]
        elif kind == "RESOURCE_ACQUIRED":
            key = _validate_resource_key(payload["resource_key"])
            task = tasks.get(payload["task_id"])
            if not task or task["status"] not in {"CLAIMED", "RUNNING"}:
                raise ValueError("resource lease requires an active claimed/running task")
            task_lease = task.get("task_lease") or {}
            if task_lease.get("status") != "ACTIVE" or task_lease.get("owner") != payload["owner"]:
                raise ValueError("resource lease owner must match the active task lease owner")
            if datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")) > datetime.fromisoformat(task_lease["expires_at"].replace("Z", "+00:00")):
                raise ValueError("resource lease cannot outlive its task lease")
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
        encoded = result.get("content") or ""
        if result.get("encoding") != "base64" or not encoded:
            blob_url = result.get("git_url")
            if not isinstance(blob_url, str) or not blob_url.startswith("https://api.github.com/repos/"):
                raise StorageError("large state response omitted a valid Git blob URL")
            blob = self._request("GET", blob_url)
            if not isinstance(blob, dict) or blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
                raise StorageError("Git blob API did not return base64 content")
            encoded = blob["content"]
        raw = base64.b64decode(encoded, validate=False)
        if len(raw) > MAX_LEGACY_STATE_BYTES:
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




MAX_SEGMENT_BYTES = 40_000_000
MAX_CAS_ATTEMPTS = 8
CAS_RETRY_BASE_SECONDS = 0.25
SEGMENT_MANIFEST_PATH = "storage/v2/state/manifest.json"
SEGMENT_DIRECTORY = "storage/v2/state/segments"


class GitHubSegmentedBackend(GitHubContentsBackend):
    """Append-only JSONL event segments committed atomically with their manifest."""

    def _head_and_tree(self):
        url = "https://api.github.com/repos/" + self.repository + "/git/ref/heads/" + urllib.parse.quote(self.branch, safe="")
        ref = self._request("GET", url)
        if not isinstance(ref, dict) or not isinstance(ref.get("object"), dict):
            raise StorageError("could not resolve storage branch head")
        head = ref["object"].get("sha")
        commit = self._request("GET", "https://api.github.com/repos/" + self.repository + "/git/commits/" + str(head))
        if not isinstance(commit, dict) or not isinstance(commit.get("tree"), dict):
            raise StorageError("could not resolve storage branch tree")
        return head, commit["tree"]["sha"]

    def _tree_entry(self, root_sha, path):
        current = root_sha
        parts = path.split("/")
        for index, part in enumerate(parts):
            tree = self._request("GET", "https://api.github.com/repos/" + self.repository + "/git/trees/" + current)
            if not isinstance(tree, dict) or tree.get("truncated"):
                raise StorageError("Git tree listing is unavailable or truncated")
            entry = next((x for x in tree.get("tree", []) if x.get("path") == part), None)
            if entry is None:
                return None
            if index == len(parts) - 1:
                return entry
            if entry.get("type") != "tree":
                return None
            current = entry["sha"]
        return None

    def _read_blob(self, blob_sha):
        blob = self._request("GET", "https://api.github.com/repos/" + self.repository + "/git/blobs/" + blob_sha)
        if not isinstance(blob, dict) or blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise StorageError("Git blob API did not return base64 content")
        try:
            # GitHub's Git Blob API may wrap base64 content across lines.
            # Strip transport whitespace first, then keep strict alphabet/padding validation.
            encoded = "".join(blob["content"].split())
            return base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise StorageError("Git blob base64 content is invalid") from exc

    def _read_at_head(self, head, root_sha):
        manifest_entry = self._tree_entry(root_sha, SEGMENT_MANIFEST_PATH)
        if manifest_entry is not None:
            if manifest_entry.get("type") != "blob":
                raise StorageError("segmented manifest path is not a blob")
            try:
                manifest = json.loads(self._read_blob(manifest_entry["sha"]).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise StorageError("segmented manifest is invalid JSON") from exc
            if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
                raise StorageError("unsupported segmented event manifest schema")
            unsigned = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
            if manifest.get("manifest_sha256") != sha256(canonical_bytes(unsigned)):
                raise StorageError("manifest SHA-256 mismatch")
            records = manifest.get("segments")
            if not isinstance(records, list) or manifest.get("segment_count") != len(records):
                raise StorageError("manifest segment count mismatch")
            directory_entry = self._tree_entry(root_sha, SEGMENT_DIRECTORY)
            if records and (directory_entry is None or directory_entry.get("type") != "tree"):
                raise StorageError("manifest references a missing segment directory")
            directory = {}
            if directory_entry is not None:
                listing = self._request("GET", "https://api.github.com/repos/" + self.repository + "/git/trees/" + directory_entry["sha"])
                if not isinstance(listing, dict) or listing.get("truncated"):
                    raise StorageError("segment directory listing is unavailable or truncated")
                directory = {x.get("path"): x for x in listing.get("tree", [])}
            events, segments = [], []
            expected_sequence = 1
            for index, record in enumerate(records, start=1):
                name = "segment-" + str(index).zfill(8) + ".jsonl"
                path = SEGMENT_DIRECTORY + "/" + name
                if not isinstance(record, dict) or record.get("index") != index or record.get("path") != path:
                    raise StorageError("manifest segment order or path is invalid")
                entry = directory.get(name)
                if entry is None or entry.get("type") != "blob" or entry.get("sha") != record.get("git_blob_sha"):
                    raise StorageError("manifest segment Git blob is missing or mismatched")
                raw = self._read_blob(entry["sha"])
                if len(raw) > MAX_SEGMENT_BYTES or len(raw) != record.get("byte_count"):
                    raise StorageError("segment byte count exceeds the limit or does not match")
                if sha256(raw) != record.get("sha256"):
                    raise StorageError("segment SHA-256 mismatch")
                lines = raw.splitlines()
                if not lines or len(lines) != record.get("record_count"):
                    raise StorageError("segment record count mismatch")
                decoded = []
                for line in lines:
                    try:
                        event = json.loads(line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise StorageError("segment contains invalid JSONL") from exc
                    if not isinstance(event, dict) or event.get("sequence") != expected_sequence:
                        raise StorageError("event sequence is discontinuous")
                    decoded.append(event)
                    events.append(event)
                    expected_sequence += 1
                if record.get("first_sequence") != decoded[0]["sequence"] or record.get("last_sequence") != decoded[-1]["sequence"]:
                    raise StorageError("segment sequence range mismatch")
                segments.append({"metadata": copy.deepcopy(record), "raw": raw})
            if manifest.get("revision") != len(events) or manifest.get("total_event_count") != len(events):
                raise StorageError("manifest aggregate event count mismatch")
            terminal = events[-1]["event_sha256"] if events else "0" * 64
            if manifest.get("last_event_sha256") != terminal:
                raise StorageError("manifest terminal event hash mismatch")
            state = {"schema_version": 1, "epoch_id": manifest.get("epoch_id"),
                     "revision": len(events), "events": events, "created_at": manifest.get("created_at")}
            return validate_state(state), manifest, segments, False

        legacy = self._tree_entry(root_sha, STATE_PATH)
        if legacy is None:
            return None, None, [], False
        if legacy.get("type") != "blob":
            raise StorageError("legacy state path is not a blob")
        raw = self._read_blob(legacy["sha"])
        if len(raw) > MAX_STATE_BYTES:
            raise StorageError("legacy state exceeds the migration read limit")
        try:
            state = validate_state(json.loads(raw.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise StorageError("legacy state failed integrity validation") from exc
        return state, None, [], True

    def read(self):
        head, root_sha = self._head_and_tree()
        state, _, _, _ = self._read_at_head(head, root_sha)
        return state, head if state is not None else None

    def _create_blob(self, raw):
        result = self._request("POST", "https://api.github.com/repos/" + self.repository + "/git/blobs",
                               {"content": base64.b64encode(raw).decode("ascii"), "encoding": "base64"})
        if not isinstance(result, dict) or not isinstance(result.get("sha"), str):
            raise StorageError("GitHub did not return a new segment blob SHA")
        return result["sha"]

    def compare_and_swap(self, candidate, *, expected_revision, expected_blob_sha, message, allow_legacy_migration=False):
        validate_state(candidate)
        head, root_sha = self._head_and_tree()
        current, manifest, segments, legacy = self._read_at_head(head, root_sha)
        current_revision = current["revision"] if current is not None else -1
        current_token = head if current is not None else None
        if current_revision != expected_revision or current_token != expected_blob_sha:
            raise Conflict("segmented event log compare-and-swap failed")
        migration_only = bool(current is not None and legacy and allow_legacy_migration and candidate == current)
        if migration_only:
            if candidate.get("revision") != expected_revision:
                raise Conflict("legacy migration must preserve the current event revision")
        else:
            if candidate.get("revision") != expected_revision + 1:
                raise ValueError("candidate revision must advance exactly once")
            if current is not None and candidate["events"][:-1] != current["events"]:
                raise Conflict("candidate does not preserve the complete event prefix")
            if current is None and candidate.get("revision") != 0:
                raise Conflict("first segmented event-log commit must initialize revision zero")

        changed, old_records = [], []
        if current is not None and not legacy:
            old_records = [copy.deepcopy(x["metadata"]) for x in segments]
            changed = [(x["metadata"]["path"], x["raw"]) for x in segments]
            events_to_append, created_at = [candidate["events"][-1]], manifest["created_at"]
        elif current is not None:
            events_to_append, created_at = candidate["events"], current["created_at"]
        else:
            events_to_append, created_at = [], candidate["created_at"]

        for event in events_to_append:
            line = canonical_bytes(event) + b"\n"
            if len(line) > MAX_SEGMENT_BYTES:
                raise StorageError("single event exceeds the 40 MB segment limit")
            if changed and len(changed[-1][1]) + len(line) <= MAX_SEGMENT_BYTES:
                path, raw = changed[-1]
                changed[-1] = (path, raw + line)
            else:
                index = len(changed) + 1
                path = SEGMENT_DIRECTORY + "/segment-" + str(index).zfill(8) + ".jsonl"
                changed.append((path, line))

        records, tree_entries = [], []
        for index, (path, raw) in enumerate(changed, start=1):
            assert_automation_write_allowed(path, "storage_management")
            old = old_records[index - 1] if index <= len(old_records) else None
            if old and old.get("byte_count") == len(raw) and old.get("sha256") == sha256(raw):
                blob_sha = old["git_blob_sha"]
            else:
                blob_sha = self._create_blob(raw)
            if not raw or len(raw) > MAX_SEGMENT_BYTES:
                raise StorageError("segment is empty or exceeds the 40 MB limit")
            decoded = [json.loads(line.decode("utf-8")) for line in raw.splitlines()]
            record = {"index": index, "path": path, "first_sequence": decoded[0]["sequence"],
                      "last_sequence": decoded[-1]["sequence"], "record_count": len(decoded),
                      "byte_count": len(raw), "sha256": sha256(raw), "git_blob_sha": blob_sha}
            records.append(record)
            tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})

        unsigned = {"schema_version": 1, "epoch_id": candidate["epoch_id"],
                    "revision": candidate["revision"], "total_event_count": len(candidate["events"]),
                    "segment_count": len(records),
                    "last_event_sha256": candidate["events"][-1]["event_sha256"] if candidate["events"] else "0" * 64,
                    "created_at": created_at, "updated_at": utc_now(), "segments": records}
        assert_automation_write_allowed(SEGMENT_MANIFEST_PATH, "storage_management")
        if legacy:
            assert_automation_write_allowed(STATE_PATH, "storage_management")
        manifest_out = dict(unsigned)
        manifest_out["manifest_sha256"] = sha256(canonical_bytes(unsigned))
        manifest_raw = (json.dumps(manifest_out, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        manifest_blob = self._create_blob(manifest_raw)
        tree_entries.append({"path": SEGMENT_MANIFEST_PATH, "mode": "100644", "type": "blob", "sha": manifest_blob})
        if legacy:
            tree_entries.append({"path": STATE_PATH, "mode": "100644", "type": "blob", "sha": None})

        tree = self._request("POST", "https://api.github.com/repos/" + self.repository + "/git/trees",
                             {"base_tree": root_sha, "tree": tree_entries})
        if not isinstance(tree, dict) or not isinstance(tree.get("sha"), str):
            raise StorageError("GitHub did not create the segmented event tree")
        commit = self._request("POST", "https://api.github.com/repos/" + self.repository + "/git/commits",
                               {"message": message, "tree": tree["sha"], "parents": [head]})
        if not isinstance(commit, dict) or not isinstance(commit.get("sha"), str):
            raise StorageError("GitHub did not create the segmented event commit")
        ref_url = "https://api.github.com/repos/" + self.repository + "/git/refs/heads/" + urllib.parse.quote(self.branch, safe="")
        self._request("PATCH", ref_url, {"sha": commit["sha"], "force": False})
        verified, _ = self.read()
        if verified is None or verified["revision"] < candidate["revision"] or verified["events"][:candidate["revision"]] != candidate["events"]:
            raise StorageError("segmented event log read-back verification failed")
        return commit["sha"]


def apply_watchdog_recovery_plan(state: dict, plan: dict, *, actor: str) -> tuple[dict, dict]:
    """Apply one read-only Watchdog plan to an in-memory state as Storage Management.

    The plan carries lease references, never task lease tokens. Tokens are
    rehydrated from the current canonical projection immediately before append.
    """
    assert_automation_write_allowed("storage/v2/state.json", actor)
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("unsupported Watchdog recovery plan schema")
    if plan.get("dispatch_enabled") is not False:
        raise PermissionError("Watchdog recovery plans cannot enable worker dispatch")
    if plan.get("epoch_id") != state.get("epoch_id"):
        raise Conflict("Watchdog plan epoch does not match current Storage state")
    if plan.get("expected_revision") != state.get("revision"):
        raise Conflict("Watchdog plan revision is stale")
    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise ValueError("Watchdog plan actions must be an array")
    observed_at = plan.get("observed_at")
    _require_timestamp(observed_at, "observed_at")
    candidate = state
    applied = []
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Watchdog action must be an object")
        if "token" in action:
            raise PermissionError("opaque task lease tokens must never be included in Watchdog plans")
        if action.get("apply_via") != "storage_management":
            raise PermissionError("recovery action must be applied by Storage Management")
        if action.get("expected_revision") != candidate.get("revision"):
            raise Conflict("Watchdog action expected revision is stale")
        event_type = action.get("event_type")
        projection = project(candidate)
        payload = None
        if event_type == "RESOURCE_LEASE_EXPIRED":
            key = _validate_resource_key(action.get("resource_key"))
            lease = projection["resource_leases"].get(key) or {}
            if (lease.get("status") != "ACTIVE"
                    or lease.get("lease_id") != action.get("lease_id")
                    or lease.get("fencing_token") != action.get("fencing_token")):
                raise Conflict("resource lease changed since Watchdog observed it")
            payload = {
                "resource_key": key,
                "lease_id": lease["lease_id"],
                "fencing_token": lease["fencing_token"],
            }
        elif event_type in {"TASK_LEASE_EXPIRED", "TASK_REQUEUED"}:
            task_id = action.get("task_id")
            task = projection["tasks"].get(task_id) or {}
            lease = task.get("task_lease") or {}
            if (lease.get("lease_id") != action.get("lease_id")
                    or lease.get("owner") != action.get("owner")
                    or not isinstance(lease.get("token"), str) or not lease["token"]):
                raise Conflict("task lease changed since Watchdog observed it")
            if event_type == "TASK_LEASE_EXPIRED":
                if lease.get("status") != "ACTIVE":
                    raise Conflict("only an active task lease can be expired")
            else:
                if lease.get("status") not in {"EXPIRED", "RELEASED"}:
                    raise Conflict("task requeue requires an expired or released lease")
            payload = {
                "task_id": task_id,
                "lease_id": lease["lease_id"],
                "owner": lease["owner"],
                "token": lease["token"],
            }
            if event_type == "TASK_REQUEUED":
                payload["reason"] = action.get("reason", "Watchdog recovery")
        elif event_type == "TASK_DEAD_LETTER":
            payload = {
                "task_id": action.get("task_id"),
                "reason": action.get("reason", "Watchdog recovery: retry budget exhausted"),
            }
        else:
            raise ValueError("unsupported Watchdog recovery event: " + str(event_type))
        idempotency_key = action.get("idempotency_key")
        _require_text({"idempotency_key": idempotency_key}, "idempotency_key")
        candidate, result = append_event(
            candidate,
            event_type=event_type,
            payload=payload,
            actor=actor,
            idempotency_key=idempotency_key,
            expected_revision=candidate["revision"],
            created_at=observed_at,
        )
        applied.append({
            "event_type": event_type,
            "revision": candidate["revision"],
            "event_sha256": result["event"]["event_sha256"],
        })
    return candidate, {
        "applied_count": len(applied),
        "applied_actions": applied,
        "final_revision": candidate["revision"],
        "epoch_id": candidate["epoch_id"],
    }


def apply_watchdog_recovery_plan_to_backend(backend, plan: dict, *, actor: str) -> dict:
    """Apply a plan through one verified GitHub Contents CAS per event.

    A concurrent update stops the sequence immediately. Already committed
    events remain valid and the caller must re-read/re-plan from the new state.
    """
    assert_automation_write_allowed("storage/v2/state.json", actor)
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("unsupported Watchdog recovery plan schema")
    if plan.get("dispatch_enabled") is not False:
        raise PermissionError("Watchdog recovery plans cannot enable worker dispatch")
    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise ValueError("Watchdog plan actions must be an array")
    base_revision = plan.get("expected_revision")
    if isinstance(base_revision, bool) or not isinstance(base_revision, int) or base_revision < 0:
        raise ValueError("Watchdog plan expected_revision must be a non-negative integer")
    _require_timestamp(plan.get("observed_at"), "observed_at")
    for index, action in enumerate(actions):
        if not isinstance(action, dict) or action.get("expected_revision") != base_revision + index:
            raise Conflict("Watchdog action revisions are not a contiguous plan")
        if "token" in action or action.get("apply_via") != "storage_management":
            raise PermissionError("Watchdog plan contains a secret or unauthorized apply target")
    state, blob_sha = backend.read()
    if state is None:
        raise Conflict("V2 storage epoch is not initialized")
    if base_revision != state.get("revision"):
        raise Conflict("Watchdog plan revision is stale")
    if plan.get("epoch_id") != state.get("epoch_id"):
        raise Conflict("Watchdog plan epoch is stale")
    applied = []
    for action in actions:
        single_plan = {
            **plan,
            "expected_revision": state["revision"],
            "actions": [{**action, "expected_revision": state["revision"]}],
        }
        candidate, summary = apply_watchdog_recovery_plan(state, single_plan, actor=actor)
        if candidate["revision"] == state["revision"]:
            continue
        blob_sha = backend.compare_and_swap(
            candidate,
            expected_revision=state["revision"],
            expected_blob_sha=blob_sha,
            message="storage(v2): apply Watchdog recovery event " + action["event_type"],
        )
        state = candidate
        applied.extend(summary["applied_actions"])
    return {
        "applied_count": len(applied),
        "applied_actions": applied,
        "final_revision": state["revision"],
        "blob_sha": blob_sha,
        "epoch_id": state["epoch_id"],
    }

def assert_automation_write_allowed(path: str, actor: str) -> None:
    """Only Storage Management may write its exact data/output scopes.

    Human repository edits use normal GitHub permissions and are deliberately
    outside this automation-only policy.
    """
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or ".." in normalized.split("/") or "\\" in path:
        raise ValueError("unsafe repository path")
    if actor == "human_user":
        return
    if normalized == "modules/uu.conf" or normalized.startswith("modules/"):
        raise PermissionError("automated workflows cannot write modules or modules/uu.conf")
    if actor != "storage_management":
        raise PermissionError(f"{actor} cannot write repository files directly")
    exact = {
        "storage/v2/state.json",
        "storage/v2/state/manifest.json",
        "rulesets/direct.list", "rulesets/proxy.list", "rulesets/reject.list",
        "rulesets/manifest.json", "rulesets/lifecycle_state.json",
        "rulesets/lifecycle_observations.json", "automation/release_manifest.json",
    }
    if normalized in exact:
        return
    parts = normalized.split("/")
    if (len(parts) == 5 and parts[:4] == ["storage", "v2", "state", "segments"]
            and re.fullmatch(r"segment-[0-9]{8}\.jsonl", parts[4])):
        return
    if (len(parts) == 5 and parts[:4] == ["storage", "v2", "artifacts", "catalog"]
            and re.fullmatch(r"[0-9]{1,20}\.json", parts[4])):
        return
    if (len(parts) == 5 and parts[:4] == ["storage", "v2", "artifacts", "sha256"]
            and re.fullmatch(r"[0-9a-f]{64}", parts[4])):
        return
    if (len(parts) == 5 and parts[:4] == ["storage", "v2", "migration", "manifests"]
            and parts[4].endswith(".json") and re.fullmatch(r"[0-9a-f]{64}", parts[4][:-5])):
        return
    if (len(parts) == 4 and parts[:3] == ["storage", "v2", "projections"]
            and parts[3].endswith(".json") and re.fullmatch(r"[a-z0-9_-]{1,80}", parts[3][:-5])):
        return
    if (len(parts) == 4 and parts[:3] == ["storage", "v2", "releases"]
            and parts[3].endswith(".json") and re.fullmatch(r"[0-9a-f]{64}", parts[3][:-5])):
        return
    raise PermissionError(f"automated write path is not allowlisted: {normalized}")


def initialize_segmented_store(backend, *, epoch_id: str, actual_seed_sha: str, approved_seed_sha: str, max_attempts: int = MAX_CAS_ATTEMPTS)
    """Initialize or migrate the event log with bounded retries on main-ref CAS races.

    Storage Management has other legitimate main-branch writers. A non-force ref
    update can therefore lose a race even when the V2 event state itself did not
    change. Re-read the canonical head and rebuild the Git tree on each retry.
    """
    if not secrets.compare_digest(actual_seed_sha, approved_seed_sha):
        raise ValueError("approved seed SHA does not match checked-in V2 seed")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")

    for attempt in range(max_attempts):
        current, current_head = backend.read()
        if current is not None:
            head, root_sha = backend._head_and_tree()
            observed, _, _, legacy = backend._read_at_head(head, root_sha)
            if observed is None or observed != current:
                if attempt + 1 == max_attempts:
                    raise Conflict("V2 state changed while preparing initialization/migration")
                continue
            if not legacy:
                return {
                    "initialized": False, "already_initialized": True,
                    "epoch_id": current["epoch_id"], "revision": current["revision"],
                    "seed_sha256": actual_seed_sha,
                }
            try:
                backend.compare_and_swap(
                    current, expected_revision=current["revision"],
                    expected_blob_sha=current_head,
                    message="chore(v2): migrate legacy state to verified segments",
                    allow_legacy_migration=True,
                )
            except Conflict:
                if attempt + 1 == max_attempts:
                    raise
                time.sleep(min(CAS_RETRY_BASE_SECONDS * (2 ** attempt), 2.0))
                continue
            verified, _ = backend.read()
            verify_head, verify_tree = backend._head_and_tree()
            replayed, _, _, still_legacy = backend._read_at_head(verify_head, verify_tree)
            if (still_legacy or replayed is None or replayed["epoch_id"] != current["epoch_id"]
                    or replayed["revision"] < current["revision"]
                    or replayed["events"][:current["revision"]] != current["events"]):
                raise StorageError("legacy migration read-back did not preserve the complete event history")
            return {
                "initialized": False, "migrated": True,
                "epoch_id": replayed["epoch_id"], "revision": replayed["revision"],
                "event_count": len(replayed["events"]), "seed_sha256": actual_seed_sha,
            }

        candidate = empty_state(epoch_id)
        try:
            backend.compare_and_swap(
                candidate, expected_revision=-1, expected_blob_sha=None,
                message="chore(v2): initialize storage epoch",
            )
        except Conflict:
            if attempt + 1 == max_attempts:
                raise
            time.sleep(min(CAS_RETRY_BASE_SECONDS * (2 ** attempt), 2.0))
            continue
        verified, _ = backend.read()
        verify_head, verify_tree = backend._head_and_tree()
        replayed, _, _, legacy = backend._read_at_head(verify_head, verify_tree)
        if (legacy or replayed is None or replayed["epoch_id"] != candidate["epoch_id"]
                or replayed["revision"] < candidate["revision"]
                or replayed["events"][:candidate["revision"]] != candidate["events"]):
            raise StorageError("new segmented event store failed read-back replay verification")
        return {
            "initialized": True, "epoch_id": replayed["epoch_id"],
            "revision": replayed["revision"], "event_count": len(replayed["events"]),
            "seed_sha256": actual_seed_sha,
        }

    raise Conflict("V2 initialization/migration exhausted its bounded CAS retries")


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
    sub.add_parser("seed-sha", help="print the canonical SHA-256 of the checked-in empty V2 seed")
    append = sub.add_parser("append")
    append.add_argument("--event-type", required=True, choices=sorted(EVENT_TYPES))
    append.add_argument("--payload", required=True)
    append.add_argument("--actor", required=True)
    append.add_argument("--idempotency-key", required=True)
    append.add_argument("--expected-revision", required=True, type=int)
    args = parser.parse_args()
    try:
        seed_path = Path(__file__).with_name("queue_seed.json")
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        actual_seed_sha = sha256(canonical_bytes(seed))
        if args.command == "seed-sha":
            print(actual_seed_sha)
            return 0
        backend = GitHubSegmentedBackend(args.repository, args.branch, args.token)
        if args.command == "init":
            result = initialize_segmented_store(
                backend, epoch_id=args.epoch_id, actual_seed_sha=actual_seed_sha,
                approved_seed_sha=args.approved_seed_sha,
            )
            print(json.dumps(result, sort_keys=True))
        elif args.command == "read":
            state, blob_sha = backend.read()
            if state is None:
                raise NotInitialized("V2 storage has not been initialized")
            print(json.dumps({"state": state, "projection": project(state), "blob_sha": blob_sha}, ensure_ascii=False))
        else:
            payload = json.loads(args.payload)
            created_at = utc_now()
            result = None
            for attempt in range(MAX_CAS_ATTEMPTS):
                state, head_sha = backend.read()
                if state is None:
                    raise NotInitialized("V2 storage has not been initialized")
                if attempt == 0 and state["revision"] != args.expected_revision:
                    already_recorded = any(event["idempotency_key"] == args.idempotency_key for event in state["events"])
                    if not already_recorded:
                        raise Conflict(f"revision conflict: expected {args.expected_revision}, current {state['revision']}")
                candidate, result = append_event(
                    state, event_type=args.event_type, payload=payload,
                    actor=args.actor, idempotency_key=args.idempotency_key,
                    expected_revision=state["revision"], created_at=created_at,
                )
                if not result["created"]:
                    break
                try:
                    backend.compare_and_swap(
                        candidate, expected_revision=state["revision"],
                        expected_blob_sha=head_sha,
                        message=f"chore(v2): append {args.event_type}",
                    )
                    break
                except Conflict:
                    if attempt == MAX_CAS_ATTEMPTS - 1:
                        raise
                    time.sleep(min(CAS_RETRY_BASE_SECONDS * (2 ** attempt), 2.0))
                    continue
            print(json.dumps(result, ensure_ascii=False))
    except (StorageError, ValueError, OSError, PermissionError) as exc:
        print(f"storage-v2: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
