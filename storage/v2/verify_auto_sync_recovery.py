#!/usr/bin/env python3
"""Fail-closed verification before reconciling Auto Sync incident history."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

AUTO_SYNC_WORKFLOW_ID = 402712272
AUTO_SYNC_WORKFLOW_PATH = ".github/workflows/auto_sync.yml"
PUBLISH_VERIFY_STEP = "Independently verify committed remote rulesets"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def verify_auto_sync_recovery(
    run: dict[str, Any],
    jobs_payload: dict[str, Any] | list[dict[str, Any]],
    queue: dict[str, Any],
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
    matching = [
        task for task in tasks
        if isinstance(task, dict)
        and str(
            (task.get("result") or {}).get("run_evidence", {}).get("run_id", "")
        ) == run_id
    ]
    if len(matching) != 1:
        reasons.append("matching_verified_queue_task_missing_or_ambiguous")
        task = {}
    else:
        task = matching[0]
    intent = task.get("dispatch_intent") if isinstance(task, dict) else None
    result = task.get("result") if isinstance(task, dict) else None
    evidence = result.get("run_evidence") if isinstance(result, dict) else None
    verification = task.get("verification") if isinstance(task, dict) else None
    if task.get("status") != "SUCCEEDED":
        reasons.append("queue_task_not_succeeded")
    if not isinstance(verification, dict) or verification.get("status") != "passed":
        reasons.append("independent_queue_verification_missing")
    if not isinstance(intent, dict) or (
        intent.get("workflow_id") != AUTO_SYNC_WORKFLOW_ID
        or intent.get("workflow_path") != AUTO_SYNC_WORKFLOW_PATH
        or not isinstance(intent.get("requested_head_sha"), str)
        or not SHA_RE.fullmatch(intent.get("requested_head_sha", ""))
    ):
        reasons.append("queue_dispatch_identity_invalid")
    if not isinstance(result, dict) or (
        result.get("workflow_id") != AUTO_SYNC_WORKFLOW_ID
        or result.get("workflow_path") != AUTO_SYNC_WORKFLOW_PATH
    ):
        reasons.append("queue_result_identity_invalid")
    if not isinstance(evidence, dict) or (
        evidence.get("status") != "completed"
        or evidence.get("conclusion") != "success"
        or str(evidence.get("run_id", "")) != run_id
        or evidence.get("head_sha") != head_sha
        or evidence.get("requested_head_sha") != (intent or {}).get("requested_head_sha")
        or evidence.get("head_sha_relationship") not in {"exact", "queue_intent_commit_only"}
    ):
        reasons.append("queue_run_evidence_mismatch")

    return {
        "verified": not reasons,
        "run_id": run_id,
        "source_sha": head_sha,
        "run_url": run_url,
        "task_id": task.get("task_id") if isinstance(task, dict) else None,
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
    result = verify_auto_sync_recovery(run, jobs, queue)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
