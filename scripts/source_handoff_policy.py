"""Deterministic de-duplication policy for Discovery -> Assessment handoffs."""
from __future__ import annotations

import hashlib
from pathlib import Path


DISCOVERY_PIPELINE_REVISION_PATHS = (
    ".github/workflows/automation-watchdog.yml",
    ".github/workflows/source-discovery.yml",
    "automation/capability_contracts/assess_sources.json",
    "automation/execution_adapters.json",
    "automation/program_registry.json",
    "scripts/assess_sources.py",
    "scripts/discover_sources.py",
    "scripts/github_queue_store.py",
    "scripts/github_workflow_adapter.py",
    "scripts/json_document_store.py",
    "scripts/remote_task_queue_runtime.py",
    "scripts/resolve_source_artifacts.py",
    "scripts/resource_lease_runtime.py",
    "scripts/source_handoff_policy.py",
    "scripts/task_queue.py",
    "scripts/task_result_verifier.py",
    "scripts/task_scheduler.py",
    "scripts/verify_assess_sources_artifacts.py",
)


def discovery_pipeline_revision(root: Path | None = None) -> str:
    """Fingerprint every implementation and contract in the independent source DAG.

    The daily Discovery idempotency key must change when queue, scheduler,
    handoff, fencing, Assessment, or verification code changes—not only when
    the producer script changes. This permits one fresh same-day run after a
    DAG implementation change while preserving deduplication for an unchanged
    pipeline revision.
    """
    repository_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for relative in DISCOVERY_PIPELINE_REVISION_PATHS:
        path = (repository_root / relative).resolve()
        if not path.is_relative_to(repository_root) or not path.is_file():
            raise ValueError(f"Discovery pipeline revision input is missing or unsafe: {relative}")
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:12]


ACTIVE_ASSESSMENT_STATUSES = {"QUEUED", "CLAIMED", "VERIFYING"}


def discovery_task_requires_handoff(task: dict, tasks: list) -> bool:
    """Return whether a Discovery task still blocks the next scheduled cycle.

    A terminal SUCCEEDED Discovery task is reconciled only until its exact
    predecessor run has one independently verified, non-activating Assessment.
    Once that proof exists, retaining the historical task must not block the
    next daily Discovery idempotency key forever.
    """
    if not isinstance(task, dict) or task.get("target_program_id") != "workflow_source_discovery":
        return False
    status = task.get("status")
    if status not in {"VERIFYING", "COMPLETED", "SUCCEEDED"}:
        return False
    if status != "SUCCEEDED":
        return True

    result = task.get("result")
    evidence = result.get("run_evidence") if isinstance(result, dict) else None
    run_id = evidence.get("run_id") if isinstance(evidence, dict) else None
    if isinstance(run_id, int) and not isinstance(run_id, bool):
        run_id = str(run_id)
    if not isinstance(run_id, str) or not run_id.isdigit():
        # Missing run evidence must remain visible to the exact-run resolver.
        return True
    if classify_assessment_handoff(tasks, run_id).get("state") == "already_assessed":
        return False

    # A newer Discovery run with a verified Assessment supersedes this older
    # unassessed snapshot. This prevents a failed historical artifact from
    # blocking the next unattended discovery cycle forever.
    created_at = str(task.get("created_at") or "")
    for newer in tasks:
        if (not isinstance(newer, dict)
                or newer.get("target_program_id") != "workflow_source_discovery"
                or newer.get("status") != "SUCCEEDED"
                or str(newer.get("created_at") or "") <= created_at):
            continue
        newer_result = newer.get("result")
        newer_evidence = newer_result.get("run_evidence") if isinstance(newer_result, dict) else None
        newer_run_id = newer_evidence.get("run_id") if isinstance(newer_evidence, dict) else None
        if isinstance(newer_run_id, int) and not isinstance(newer_run_id, bool):
            newer_run_id = str(newer_run_id)
        if (isinstance(newer_run_id, str) and newer_run_id.isdigit()
                and classify_assessment_handoff(tasks, newer_run_id).get("state") == "already_assessed"):
            return False
    return True


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
