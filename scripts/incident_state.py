#!/usr/bin/env python3
"""Deterministic, idempotent incident-state transitions stored in GitHub issue bodies."""
from __future__ import annotations


import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

STATES = {
    "HEALTHY", "DETECTED", "DIAGNOSING", "RECOVERING",
    "VERIFYING", "RECOVERED", "MANUAL_INTERVENTION",
}
TRANSITIONS = {
    "HEALTHY": {"DETECTED"},
    "DETECTED": {"DIAGNOSING", "MANUAL_INTERVENTION"},
    "DIAGNOSING": {"RECOVERING", "MANUAL_INTERVENTION"},
    "RECOVERING": {"VERIFYING", "MANUAL_INTERVENTION"},
    "VERIFYING": {"RECOVERED", "RECOVERING", "MANUAL_INTERVENTION"},
    "MANUAL_INTERVENTION": {"DIAGNOSING", "RECOVERING", "VERIFYING"},
    "RECOVERED": {"DETECTED"},
}
START = "<!-- shadowrocket-incident-state:v1"
END = "-->"
BLOCK_RE = re.compile(
    r"<!-- shadowrocket-incident-state:v1\n(.*?)\n-->",
    re.DOTALL,
)


class IncidentStateError(ValueError):
    """Raised when an incident transition is invalid or unsafe."""


def incident_key(workflow: str, source_sha: str, classification: str) -> str:
    if not workflow.strip() or not classification.strip():
        raise IncidentStateError("workflow and classification are required")
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", source_sha):
        raise IncidentStateError("source_sha must be a 7-40 character hexadecimal SHA")
    raw = f"{workflow.strip()}|{source_sha.lower()}|{classification.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _read_state(body: str) -> tuple[dict[str, Any] | None, re.Match[str] | None]:
    matches = list(BLOCK_RE.finditer(body))
    if not matches:
        return None, None
    if len(matches) != 1:
        raise IncidentStateError("incident body must contain exactly one state block")
    match = matches[0]
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise IncidentStateError("incident state block contains invalid JSON") from exc
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise IncidentStateError("unsupported incident state schema")
    if state.get("state") not in STATES:
        raise IncidentStateError("unknown incident state")

    history = state.get("history")
    if not isinstance(history, list) or not history:
        raise IncidentStateError("incident state history is missing")
    if any(item not in STATES for item in history):
        raise IncidentStateError("incident state history contains an unknown state")
    if history[-1] != state["state"]:
        raise IncidentStateError("incident state does not match the final history entry")
    for previous, current in zip(history, history[1:]):
        if current not in TRANSITIONS[previous]:
            raise IncidentStateError("incident state history contains an illegal transition")

    revision = state.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise IncidentStateError("incident revision must be a non-negative integer")

    events = state.get("processed_events")
    if not isinstance(events, list) or any(not isinstance(item, str) or not item for item in events):
        raise IncidentStateError("processed event ledger is invalid")
    if len(events) != len(set(events)):
        raise IncidentStateError("processed event ledger contains duplicate event ids")

    if state["state"] == "RECOVERED":
        verification = state.get("verification")
        if not isinstance(verification, dict):
            raise IncidentStateError("recovered incident is missing verification evidence")
        if not isinstance(verification.get("url"), str) or not verification["url"].strip():
            raise IncidentStateError("recovered incident verification URL is invalid")
        if verification.get("event_id") not in events:
            raise IncidentStateError("recovered incident verification event is not recorded")
    return state, match


def resolve_source_sha(body: str, fallback_sha: str) -> str:
    """Keep a persisted incident's original identity; use fallback only for legacy issues."""
    state, _ = _read_state(body)
    if state is not None:
        return str(state.get("source_sha", ""))
    return fallback_sha


def transition_incident(
    body: str,
    *,
    workflow: str,
    source_sha: str,
    classification: str,
    event_id: str,
    target_state: str,
    verification_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    if target_state not in STATES or target_state == "HEALTHY":
        raise IncidentStateError("target state must be an active incident state")
    if not event_id.strip():
        raise IncidentStateError("event_id is required")
    if target_state == "RECOVERED" and not verification_url:
        raise IncidentStateError("RECOVERED requires independent verification evidence")
    # Validate the caller's identity even when a persisted state block exists.
    requested_key = incident_key(workflow, source_sha, classification)

    state, match = _read_state(body)
    if state is None:
        key = incident_key(workflow, source_sha, classification)
        if target_state == "MANUAL_INTERVENTION":
            history = ["DETECTED", "DIAGNOSING"]
            initial = "DIAGNOSING"
        elif target_state in {"RECOVERING", "VERIFYING"}:
            # Bootstrap legacy incidents through an explicit diagnosed state.
            history = ["DETECTED", "DIAGNOSING", "MANUAL_INTERVENTION"]
            initial = "MANUAL_INTERVENTION"
        elif target_state == "RECOVERED":
            raise IncidentStateError("RECOVERED requires a persisted VERIFYING state")
        else:
            history = ["HEALTHY"]
            initial = "HEALTHY"
        state = {
            "schema_version": 1,
            "incident_id": key,
            "workflow": workflow,
            "source_sha": source_sha.lower(),
            "classification": classification,
            "state": initial,
            "revision": len(history) - 1,
            "history": history,
            "processed_events": [],
            "verification": None,
        }
    else:
        if state.get("workflow") != workflow:
            raise IncidentStateError("workflow does not match the persisted incident")
        if state.get("classification") != classification:
            raise IncidentStateError("classification does not match the persisted incident")
        if state.get("source_sha") != source_sha.lower():
            raise IncidentStateError("source SHA does not match the persisted incident")
        expected_key = incident_key(
            state.get("workflow", ""),
            state.get("source_sha", ""),
            state.get("classification", ""),
        )
        if state.get("incident_id") != expected_key or expected_key != requested_key:
            raise IncidentStateError("persisted incident key does not match its identity fields")
        if not isinstance(state.get("processed_events"), list):
            raise IncidentStateError("processed event ledger is invalid")

    if event_id in state["processed_events"]:
        if state["state"] != target_state:
            raise IncidentStateError("event id was already used for a different target state")
        return body, state

    current = state["state"]
    if target_state != current and target_state not in TRANSITIONS[current]:
        raise IncidentStateError(f"transition {current} -> {target_state} is not allowed")

    state["state"] = target_state
    state["revision"] = int(state.get("revision", 0)) + 1
    state["history"].append(target_state)
    state["processed_events"].append(event_id)
    state["processed_events"] = state["processed_events"][-100:]
    if target_state == "DETECTED":
        state["verification"] = None
    if target_state == "RECOVERED":
        state["verification"] = {
            "url": verification_url,
            "event_id": event_id,
        }

    block = f"{START}\n{json.dumps(state, ensure_ascii=False, sort_keys=True)}\n{END}"
    if match:
        updated = body[:match.start()] + block + body[match.end():]
    else:
        updated = body.rstrip() + "\n\n" + block + "\n"
    return updated, state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--body-file", required=True, type=Path)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-sha-from-state", action="store_true")
    parser.add_argument("--classification", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--target-state", required=True, choices=sorted(STATES - {"HEALTHY"}))
    parser.add_argument("--verification-url")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    body = args.body_file.read_text(encoding="utf-8")
    source_sha = resolve_source_sha(body, args.source_sha) if args.source_sha_from_state else args.source_sha
    updated, state = transition_incident(
        body,
        workflow=args.workflow,
        source_sha=source_sha,
        classification=args.classification,
        event_id=args.event_id,
        target_state=args.target_state,
        verification_url=args.verification_url,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(updated, encoding="utf-8")
    print(json.dumps({
        "incident_id": state["incident_id"],
        "state": state["state"],
        "revision": state["revision"],
        "history": state["history"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
