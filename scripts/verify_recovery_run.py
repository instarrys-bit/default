#!/usr/bin/env python3
"""Fail-closed verification of a completed deterministic audit recovery run."""
from __future__ import annotations


import argparse
import json
from pathlib import Path
from typing import Any


AUDIT_WORKFLOW = "Shadowrocket Deterministic Domain Audit (User Config Baseline)"
PUBLISH_VERIFY_STEP = "Independently verify committed remote rulesets"


def verify_recovery_run(run: dict[str, Any], jobs_payload: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if run.get("status") != "completed":
        reasons.append("run_not_completed")
    if run.get("conclusion") != "success":
        reasons.append("run_not_successful")
    if run.get("head_branch") != "main":
        reasons.append("run_not_main_branch")
    if run.get("name") != AUDIT_WORKFLOW:
        reasons.append("unexpected_workflow")

    if isinstance(jobs_payload, list):
        pages = jobs_payload
    else:
        pages = [jobs_payload]
    jobs: list[dict[str, Any]] = []
    for page in pages:
        if isinstance(page, dict) and isinstance(page.get("jobs"), list):
            jobs.extend(job for job in page["jobs"] if isinstance(job, dict))
        else:
            reasons.append("jobs_payload_invalid")

    by_name = {job.get("name"): job for job in jobs if isinstance(job, dict)}
    audit = by_name.get("audit")
    publish = by_name.get("publish")
    if not isinstance(audit, dict) or audit.get("conclusion") != "success":
        reasons.append("audit_job_not_successful")
    if not isinstance(publish, dict) or publish.get("conclusion") != "success":
        reasons.append("publish_job_not_successful")

    verify_step_ok = False
    if isinstance(publish, dict):
        steps = publish.get("steps", [])
        verify_step_ok = any(
            isinstance(step, dict)
            and step.get("name") == PUBLISH_VERIFY_STEP
            and step.get("conclusion") == "success"
            for step in steps
        )
    if not verify_step_ok:
        reasons.append("remote_publish_verification_missing_or_failed")

    return {
        "verified": not reasons,
        "run_id": str(run.get("id", "")),
        "source_sha": run.get("head_sha", ""),
        "verification_step": PUBLISH_VERIFY_STEP,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--jobs", required=True, type=Path)
    args = parser.parse_args()

    run = json.loads(args.run.read_text(encoding="utf-8"))
    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    result = verify_recovery_run(run, jobs)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
