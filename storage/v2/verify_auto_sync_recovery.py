#!/usr/bin/env python3
"""Fail-closed verification before reconciling Auto Sync incident history."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from production_intent import compute_fingerprint, load_manifest

AUTO_SYNC_WORKFLOW_ID = 402712272
AUTO_SYNC_WORKFLOW_PATH = ".github/workflows/auto_sync.yml"
PUBLISH_VERIFY_STEP = "Independently verify committed remote rulesets"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def verify_auto_sync_recovery(
    run: dict[str, Any],
    jobs_payload: dict[str, Any] | list[dict[str, Any]],
    queue: dict[str, Any],
    current_fingerprint: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    run_id = str(run.get("id", ""))
    head_sha = run.get("head_sha", "")
    run_url = run.get("html_url", "")

    if not run_id.isdigit():
        reasons.append("run_id_invalid")
    if run.get("workflow_id") != AUTO_SYNC_WORKFLOW_ID:
        reasons.append("unexpected_workflow_id")
    if run.get("path") != AUTO_SYNC_WORKFLOW_PATH:
        reasons.append("unexpected_workflow_path")
    if run.get("event") != "workflow_dispatch":
        reasons.append("run_not_watchdog_dispatched")
    if run.get("head_branch") != "main":
        reasons.append("run_not_main_branch")
    if run.get("status") != "completed":
        reasons.append("run_not_completed")
    if run.get("conclusion") != "success":
        reasons.append("run_not_successful")
    if not isinstance(head_sha, str) or not SHA_RE.fullmatch(head_sha):
        reasons.append("run_head_sha_invalid")
    if not isinstance(run_url, str) or not run_url.startswith("https://"):
        reasons.append("run_url_invalid")
    if not isinstance(current_fingerprint, str) or not SHA256_RE.fullmatch(current_fingerprint):
        reasons.append("current_production_fingerprint_invalid")

    pages = jobs_payload if isinstance(jobs_payload, list) else [jobs_payload]
    jobs: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, dict) and isinstance(page.get("jobs"), list):
            jobs.extend(item for item in page["jobs"] if isinstance(item, dict))
        else:
            reasons.append("jobs_payload_invalid")
    by_name = {item.get("name"): item for item in jobs}
    audit = by_name.get("audit")
    publish = by_name.get("publish")
    if not isinstance(audit, dict) or audit.get("conclusion") != "success":
        reasons.append("audit_job_not_successful")
    if not isinstance(publish, dict) or publish.get("conclusion") != "success":
        reasons.append("publish_job_not_successful")
    verify_ok = isinstance(publish, dict) and any(
        isinstance(step, dict)
        and step.get("name") == PUBLISH_VERIFY_STEP
        and step.get("conclusion") == "success"
        for step in publish.get("steps", [])
    )
    if not verify_ok:
        reasons.append("remote_publish_verification_missing_or_failed")

    tasks = queue.get("tasks") if isinstance(queue, dict) else None
    if not isinstance(tasks, list):
        reasons.append("queue_tasks_invalid")
        tasks = []
    matching: list[dict[str, Any]] = []
    for candidate in tasks:
        if not isinstance(candidate, dict):
            continue
        evidence = _mapping(_mapping(candidate.get("result")).get("run_evidence"))
        if str(evidence.get("run_id", "")) == run_id:
            matching.append(candidate)
    if len(matching) != 1:
        reasons.append("matching_verified_queue_task_missing_or_ambiguous")
        task: dict[str, Any] = {}
    else:
        task = matching[0]

    intent = _mapping(task.get("dispatch_intent"))
    result = _mapping(task.get("result"))
    evidence = _mapping(result.get("run_evidence"))
    verification = _mapping(task.get("verification"))
    resource_lease = _mapping(task.get("resource_lease"))
    task_input = _mapping(task.get("input"))
    requested_sha = intent.get("requested_head_sha")
    if task.get("status") != "SUCCEEDED":
        reasons.append("queue_task_not_succeeded")
    if verification.get("status") != "passed":
        reasons.append("independent_queue_verification_missing")
    if (
        verification.get("verifier_program_id") != "script_task_result_verifier"
        or not isinstance(verification.get("contract_sha256"), str)
        or not SHA256_RE.fullmatch(verification.get("contract_sha256", ""))
    ):
        reasons.append("queue_verifier_identity_invalid")
    if (
        intent.get("workflow_id") != AUTO_SYNC_WORKFLOW_ID
        or intent.get("workflow_path") != AUTO_SYNC_WORKFLOW_PATH
        or intent.get("task_id") != task.get("task_id")
        or not isinstance(requested_sha, str)
        or not SHA_RE.fullmatch(requested_sha)
    ):
        reasons.append("queue_dispatch_identity_invalid")
    if (
        result.get("workflow_id") != AUTO_SYNC_WORKFLOW_ID
        or result.get("workflow_path") != AUTO_SYNC_WORKFLOW_PATH
        or result.get("task_id") != task.get("task_id")
        or result.get("correlation_id") != intent.get("correlation_id")
        or result.get("dispatch_attempt") != intent.get("dispatch_attempt")
    ):
        reasons.append("queue_result_identity_invalid")
    if (
        resource_lease.get("status") != "RELEASED"
        or not resource_lease.get("released_at")
    ):
        reasons.append("resource_lease_not_released")
    if (
        evidence.get("status") != "completed"
        or evidence.get("conclusion") != "success"
        or str(evidence.get("run_id", "")) != run_id
        or evidence.get("head_sha") != head_sha
        or evidence.get("requested_head_sha") != requested_sha
        or evidence.get("head_sha_relationship") not in {"exact", "queue_intent_commit_only"}
    ):
        reasons.append("queue_run_evidence_mismatch")
    if task_input.get("production_fingerprint") != current_fingerprint:
        reasons.append("queue_production_fingerprint_mismatch")

    return {
        "verified": not reasons,
        "run_id": run_id,
        "source_sha": head_sha,
        "run_url": run_url,
        "task_id": task.get("task_id"),
        "production_fingerprint": current_fingerprint,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--queue", required=True, type=Path)
    args = parser.parse_args()
    run = json.loads(args.run.read_text(encoding="utf-8"))
    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
    current_fingerprint = compute_fingerprint(ROOT, manifest)
    result = verify_auto_sync_recovery(run, jobs, queue, current_fingerprint)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
