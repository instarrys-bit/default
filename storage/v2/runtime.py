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
        "rulesets/direct.list", "rulesets/proxy.list", "rulesets/reject.list",
        "rulesets/manifest.json", "rulesets/lifecycle_state.json",
        "rulesets/lifecycle_observations.json", "automation/release_manifest.json",
    }
    if normalized in exact:
        return
    parts = normalized.split("/")
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
        backend = GitHubContentsBackend(args.repository, args.branch, args.token)
        if args.command == "init":
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
