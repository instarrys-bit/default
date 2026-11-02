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
    "MANUAL_INTERVENTION": {"DIAGNOSING", "RECOVERING", "RECOVERED"},
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
    match = BLOCK_RE.search(body)
    if not match:
        return None, None
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise IncidentStateError("incident state block contains invalid JSON") from exc
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise IncidentStateError("unsupported incident state schema")
    if state.get("state") not in STATES:
        raise IncidentStateError("unknown incident state")
    if not isinstance(state.get("history"), list) or not state["history"]:
        raise IncidentStateError("incident state history is missing")
    return state, match


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

    state, match = _read_state(body)
    if state is None:
        key = incident_key(workflow, source_sha, classification)
        if target_state == "MANUAL_INTERVENTION":
            history = ["DETECTED", "DIAGNOSING"]
            initial = "DIAGNOSING"
        elif target_state == "RECOVERED":
            # Backward-compatible bootstrap for pre-state-machine incidents.
            history = ["DETECTED", "DIAGNOSING", "MANUAL_INTERVENTION"]
            initial = "MANUAL_INTERVENTION"
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
            "revision": 0,
            "history": history,
            "processed_events": [],
            "verification": None,
        }
    else:
        if state.get("workflow") != workflow:
            raise IncidentStateError("workflow does not match the persisted incident")
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
    parser.add_argument("--classification", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--target-state", required=True, choices=sorted(STATES - {"HEALTHY"}))
    parser.add_argument("--verification-url")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    body = args.body_file.read_text(encoding="utf-8")
    updated, state = transition_incident(
        body,
        workflow=args.workflow,
        source_sha=args.source_sha,
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
