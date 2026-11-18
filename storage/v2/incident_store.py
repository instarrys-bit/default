#!/usr/bin/env python3
"""Storage Management incident ledger backed by repository JSON and Contents SHA-CAS."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from storage.v2.queue_store import GitHubContentsJsonStore
from incident_state import incident_key, transition_incident

INCIDENTS_PATH = "storage/v2/incidents.json"

def _validate_document(document: dict[str, Any]) -> None:
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("unsupported incident ledger schema")
    if isinstance(document.get("revision"), bool) or not isinstance(document.get("revision"), int):
        raise ValueError("incident ledger revision must be an integer")
    if not isinstance(document.get("incidents"), list) or not isinstance(document.get("events"), list):
        raise ValueError("incident ledger collections are malformed")

def _event_exists(document, event_id):
    return any(item.get("event_id") == event_id for item in document["events"] if isinstance(item, dict))

def record_incident(document, *, workflow, run_id, source_sha, classification, event_id, summary, run_url, diagnosis=None):
    _validate_document(document)
    if not re.fullmatch(r"[a-z0-9_-]{2,64}", workflow): raise ValueError("invalid workflow key")
    if not str(run_id).isdigit(): raise ValueError("run_id must be numeric")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_sha): raise ValueError("source_sha must be a full Git commit SHA")
    if not re.fullmatch(r"[A-Z0-9_]{2,64}", classification): raise ValueError("invalid incident classification")
    if not event_id or not summary or not run_url.startswith("https://"): raise ValueError("event_id, summary and HTTPS run_url are required")
    if _event_exists(document, event_id): return document, {"changed": False, "reason": "duplicate_event"}
    identity = incident_key(workflow, source_sha, classification)
    incident_id = f"{identity}-{run_id}"
    record = next((item for item in document["incidents"] if item.get("incident_id") == incident_id), None)
    if record is None:
        record = {"incident_id": incident_id, "identity_key": identity, "workflow": workflow, "run_id": str(run_id),
                  "source_sha": source_sha.lower(), "classification": classification, "lifecycle_status": "OPEN",
                  "body": "", "incident_state": None, "created_at": None, "updated_at": None,
                  "legacy_sources": [], "events": []}
        document["incidents"].append(record)
    body = record.get("body") or summary
    updated_body, state = transition_incident(body, workflow=workflow, source_sha=source_sha,
        classification=classification, event_id=event_id, target_state="MANUAL_INTERVENTION")
    record.update({"body": updated_body, "incident_state": state, "lifecycle_status": state["state"],
        "workflow": workflow, "run_id": str(run_id), "source_sha": source_sha.lower(),
        "classification": classification, "summary": summary, "run_url": run_url, "diagnosis": diagnosis,
        "updated_at": event_id})
    record.setdefault("events", []).append(event_id)
    if not record.get("created_at"): record["created_at"] = event_id
    document["events"].append({"event_id": event_id, "operation": "record", "incident_id": incident_id,
        "workflow": workflow, "run_id": str(run_id), "source_sha": source_sha.lower(),
        "classification": classification, "summary": summary, "run_url": run_url})
    document["revision"] += 1
    return document, {"changed": True, "incident_id": incident_id, "state": state["state"]}

def resolve_incidents(document, *, workflow, before_run_id, classifications, event_id, verification_url):
    _validate_document(document)
    if not re.fullmatch(r"[a-z0-9_-]{2,64}", workflow): raise ValueError("invalid workflow key")
    if not str(before_run_id).isdigit(): raise ValueError("before_run_id must be numeric")
    if not event_id or not verification_url.startswith("https://"): raise ValueError("event_id and HTTPS verification_url are required")
    allowed = set(classifications)
    if not allowed or any(not re.fullmatch(r"[A-Z0-9_]{2,64}", item) for item in allowed):
        raise ValueError("at least one valid classification is required")
    if _event_exists(document, event_id): return document, {"changed": False, "reason": "duplicate_event", "resolved": 0}
    resolved = []
    for record in document["incidents"]:
        if (record.get("workflow") != workflow or record.get("classification") not in allowed
            or not str(record.get("run_id", "")).isdigit() or int(record["run_id"]) >= int(before_run_id)
            or record.get("lifecycle_status") in {"RECOVERED", "CLOSED"}): continue
        source_sha = record.get("source_sha")
        if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha): continue
        body = record.get("body") or (record.get("summary") or "Legacy incident")
        state = record.get("incident_state")
        if not isinstance(state, dict) or state.get("state") not in {
            "DETECTED", "DIAGNOSING", "RECOVERING", "VERIFYING", "MANUAL_INTERVENTION", "RECOVERED"}:
            body, state = transition_incident(body, workflow=workflow, source_sha=source_sha,
                classification=record["classification"], event_id=f"legacy-detected-{record['incident_id']}",
                target_state="MANUAL_INTERVENTION")
        if state["state"] == "RECOVERED":
            record.update({"lifecycle_status": "RECOVERED", "incident_state": state, "body": body})
            continue
        verify_event = f"{event_id}:verify:{record['incident_id']}"
        recovered_event = f"{event_id}:recovered:{record['incident_id']}"
        if state["state"] != "VERIFYING":
            body, state = transition_incident(body, workflow=workflow, source_sha=source_sha,
                classification=record["classification"], event_id=verify_event, target_state="VERIFYING")
        body, state = transition_incident(body, workflow=workflow, source_sha=source_sha,
            classification=record["classification"], event_id=recovered_event,
            target_state="RECOVERED", verification_url=verification_url)
        record.update({"body": body, "incident_state": state, "lifecycle_status": "RECOVERED",
            "verification_url": verification_url, "updated_at": event_id})
        record.setdefault("events", []).extend([verify_event, recovered_event])
        resolved.append(record["incident_id"])
    document["events"].append({"event_id": event_id, "operation": "resolve", "workflow": workflow,
        "before_run_id": str(before_run_id), "classifications": sorted(allowed),
        "verification_url": verification_url, "resolved_incident_ids": resolved})
    document["revision"] += 1
    return document, {"changed": bool(resolved), "resolved": len(resolved), "incident_ids": resolved}

def _store():
    repository, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    if not repository or not token: raise RuntimeError("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
    return GitHubContentsJsonStore(repository, INCIDENTS_PATH, branch="main", token=token, bootstrap_path=INCIDENTS_PATH)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("record", "resolve"))
    parser.add_argument("--workflow", required=True); parser.add_argument("--event-id", required=True)
    parser.add_argument("--run-id"); parser.add_argument("--source-sha"); parser.add_argument("--classification")
    parser.add_argument("--summary"); parser.add_argument("--run-url"); parser.add_argument("--diagnosis-file", type=Path)
    parser.add_argument("--before-run-id"); parser.add_argument("--classifications"); parser.add_argument("--verification-url")
    args = parser.parse_args(argv)
    diagnosis = json.loads(args.diagnosis_file.read_text(encoding="utf-8")) if args.diagnosis_file else None
    def mutate(document):
        if args.operation == "record":
            return record_incident(document, workflow=args.workflow, run_id=args.run_id or "",
                source_sha=args.source_sha or "", classification=args.classification or "", event_id=args.event_id,
                summary=args.summary or "", run_url=args.run_url or "", diagnosis=diagnosis)
        return resolve_incidents(document, workflow=args.workflow, before_run_id=args.before_run_id or "",
            classifications=[x for x in (args.classifications or "").split(",") if x],
            event_id=args.event_id, verification_url=args.verification_url or "")
    result = _store().mutate(mutate)
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
