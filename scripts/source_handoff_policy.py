"""Deterministic de-duplication policy for Discovery -> Assessment handoffs."""
from __future__ import annotations


ACTIVE_ASSESSMENT_STATUSES = {"QUEUED", "CLAIMED", "VERIFYING"}


def classify_assessment_handoff(tasks: list, workflow_run_id: str) -> dict:
    """Classify all Assessment tasks tied to one immutable Discovery run.

    The predecessor run ID is authoritative. Idempotency-key matching is retained
    for older queue entries that predate the explicit predecessor field.
    """
    if not isinstance(workflow_run_id, str) or not workflow_run_id.isdigit():
        raise ValueError("workflow_run_id must be a positive decimal string")
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")

    canonical_key = f"source-assessment:{workflow_run_id}"
    versioned_prefix = canonical_key + ":"
    matches = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("target_program_id") != "script_assess_sources":
            continue
        task_input = task.get("input")
        predecessor = task_input.get("predecessor") if isinstance(task_input, dict) else None
        predecessor_run_id = predecessor.get("workflow_run_id") if isinstance(predecessor, dict) else None
        key = task.get("idempotency_key")
        legacy_key_match = (
            isinstance(key, str)
            and (key == canonical_key or key.startswith(versioned_prefix))
        )
        if predecessor_run_id == workflow_run_id or legacy_key_match:
            matches.append(task)

    matches.sort(key=lambda item: (str(item.get("created_at", "")), str(item.get("task_id", ""))))
    verified = []
    active = []
    invalid_success = []
    for task in matches:
        status = task.get("status")
        if status == "SUCCEEDED":
            verification = task.get("verification")
            result = task.get("result")
            artifact = result.get("artifact_verification") if isinstance(result, dict) else None
            if (
                isinstance(verification, dict)
                and verification.get("status") == "passed"
                and isinstance(artifact, dict)
                and artifact.get("valid") is True
                and artifact.get("activation_count") == 0
            ):
                verified.append(task)
            else:
                invalid_success.append(task)
        elif status in ACTIVE_ASSESSMENT_STATUSES:
            active.append(task)

    task_ids = [str(item.get("task_id", "")) for item in matches]
    if verified:
        canonical = verified[0]
        canonical_id = str(canonical.get("task_id", ""))
        return {
            "state": "already_assessed",
            "canonical_task_id": canonical_id,
            "task_ids": task_ids,
            "duplicate_task_ids": [task_id for task_id in task_ids if task_id != canonical_id],
            "reason": "A matching Assessment task already completed with passed verification and a valid non-activating artifact result.",
        }
    if active:
        canonical = active[0]
        canonical_id = str(canonical.get("task_id", ""))
        return {
            "state": "assessment_pending",
            "canonical_task_id": canonical_id,
            "task_ids": task_ids,
            "duplicate_task_ids": [task_id for task_id in task_ids if task_id != canonical_id],
            "reason": "A matching Assessment task is already queued, claimed, or being verified.",
        }
    if invalid_success:
        return {
            "state": "assessment_evidence_invalid",
            "canonical_task_id": str(invalid_success[0].get("task_id", "")),
            "task_ids": task_ids,
            "duplicate_task_ids": task_ids[1:],
            "reason": "A matching task says SUCCEEDED but its independent verification or non-activation artifact proof is invalid.",
        }
    if matches:
        return {
            "state": "assessment_retry_required",
            "canonical_task_id": str(matches[0].get("task_id", "")),
            "task_ids": task_ids,
            "duplicate_task_ids": task_ids[1:],
            "reason": "A prior matching Assessment task exists but is not in a verified-success or active state.",
        }
    return {
        "state": "ready",
        "canonical_task_id": "",
        "task_ids": [],
        "duplicate_task_ids": [],
        "reason": "No Assessment task exists for this exact Discovery run.",
    }
