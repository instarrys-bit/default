"""Deterministic de-duplication policy for Discovery -> Assessment handoffs."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
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


def select_source_worker_task(tasks: list, predecessor_workflow_run_id: str | None = None) -> str:
    """Select one safe source task, binding Assessment to its mounted Discovery artifact.

    The Watchdog mounts one exact Discovery artifact per run. Never select an Assessment
    task whose typed predecessor belongs to another run: its digest cannot be checked
    against the currently mounted artifact. Without an exact predecessor run ID, only
    Discovery and unrelated safe tasks may be selected.
    """
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    if predecessor_workflow_run_id is not None and (
        not isinstance(predecessor_workflow_run_id, str)
        or not predecessor_workflow_run_id.isdigit()
    ):
        raise ValueError("predecessor_workflow_run_id must be a decimal workflow run ID")
    safe = [
        task for task in tasks
        if isinstance(task, dict)
        and task.get("target_program_id") != "workflow_auto_sync"
        and task.get("status") in {"QUEUED", "CLAIMED", "VERIFYING", "SUCCEEDED"}
    ]
    runnable = [
        task for task in safe
        if task.get("status") in {"QUEUED", "CLAIMED", "VERIFYING"}
        and (
            task.get("target_program_id") != "script_assess_sources"
            or (
                predecessor_workflow_run_id is not None
                and isinstance(task.get("input"), dict)
                and isinstance(task["input"].get("predecessor"), dict)
                and task["input"]["predecessor"].get("workflow_run_id") == predecessor_workflow_run_id
            )
        )
    ]
    artifact_recovery = [
        task for task in runnable
        if task.get("target_program_id") == "script_assess_sources"
        and isinstance(task.get("idempotency_key"), str)
        and task["idempotency_key"].endswith(":artifact-recovery:1")
    ]
    if artifact_recovery:
        candidates = artifact_recovery
    else:
        discoveries = [
            task for task in safe
            if task.get("target_program_id") == "workflow_source_discovery"
        ]
        latest = max(
            discoveries,
            key=lambda task: (str(task.get("created_at") or ""), str(task.get("task_id") or "")),
            default=None,
        )
        gate_open = False
        if isinstance(latest, dict) and latest.get("status") == "SUCCEEDED":
            evidence = ((latest.get("result") or {}).get("run_evidence") or {})
            run_id = evidence.get("run_id")
            if isinstance(run_id, int) and not isinstance(run_id, bool):
                run_id = str(run_id)
            if isinstance(run_id, str) and run_id.isdigit():
                gate_open = classify_assessment_handoff(tasks, run_id).get("state") == "already_assessed"
        if gate_open:
            return ""
        discovery_queued = [
            task for task in runnable
            if task.get("target_program_id") == "workflow_source_discovery" and task.get("status") == "QUEUED"
        ]
        assessment_queued = [
            task for task in runnable
            if task.get("target_program_id") == "script_assess_sources" and task.get("status") == "QUEUED"
        ]
        active_source = [
            task for task in runnable
            if task.get("target_program_id") in {"workflow_source_discovery", "script_assess_sources"}
            and task.get("status") in {"CLAIMED", "VERIFYING"}
        ]
        # Assessment is the required predecessor of production. Never let a queued
        # next-cycle Discovery starve an Assessment tied to the currently mounted artifact.
        candidates = assessment_queued or discovery_queued or active_source or runnable
    if not candidates:
        return ""
    rank = {"QUEUED": 0, "CLAIMED": 1, "VERIFYING": 1}
    chosen = min(
        candidates,
        key=lambda task: (
            rank.get(task.get("status"), 9),
            -int(task.get("priority", 0) or 0),
            str(task.get("created_at") or ""),
            str(task.get("task_id") or ""),
        ),
    )
    return str(chosen.get("task_id") or "")

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

def latest_verified_assessed_discovery(tasks: list) -> dict | None:
    """Return the newest Discovery whose exact Assessment is independently verified.

    Newer queued, active, failed, or not-yet-assessed Discovery tasks do not
    invalidate the last usable source snapshot. They are non-activating until
    their own Assessment succeeds, so production may safely continue from the
    newest already-verified predecessor.
    """
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    eligible = []
    for task in tasks:
        if (not isinstance(task, dict)
                or task.get("target_program_id") != "workflow_source_discovery"
                or task.get("status") != "SUCCEEDED"
                or (task.get("verification") or {}).get("status") != "passed"):
            continue
        evidence = (task.get("result") or {}).get("run_evidence") or {}
        run_id = evidence.get("run_id")
        if isinstance(run_id, int) and not isinstance(run_id, bool):
            run_id = str(run_id)
        if not isinstance(run_id, str) or not run_id.isdigit():
            continue
        if classify_assessment_handoff(tasks, run_id).get("state") != "already_assessed":
            continue
        eligible.append(task)
    return max(
        eligible,
        key=lambda item: (str(item.get("created_at") or ""), str(item.get("task_id") or "")),
        default=None,
    )


def select_production_worker_task(tasks: list, current_fingerprint: str, now: datetime | None = None) -> str:
    """Select one queued production audit using the newest independently verified source snapshot.

    This is deliberately separate from select_source_worker_task: the source worker
    stops at the Assessment boundary, while this selector is the sole handoff into
    the already-reviewed production workflow adapter.
    """
    if not isinstance(tasks, list):
        raise ValueError("tasks must be a list")
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("now must be a timezone-aware datetime")
    now = now.astimezone(timezone.utc)
    if not isinstance(current_fingerprint, str) or len(current_fingerprint) != 64:
        raise ValueError("current production fingerprint must be a SHA-256 hex digest")
    latest = latest_verified_assessed_discovery(tasks)
    if not isinstance(latest, dict):
        return ""

    # An already-dispatched production task owns the pipeline until Watchdog
    # reconciles its exact workflow run; never start a second writer.
    for task in tasks:
        if (isinstance(task, dict)
                and task.get("target_program_id") == "workflow_auto_sync"
                and (task.get("status") in {"CLAIMED", "VERIFYING"}
                     or (task.get("status") == "QUEUED" and isinstance(task.get("dispatch_intent"), dict)))):
            return ""

    candidates = []
    for task in tasks:
        if (not isinstance(task, dict)
                or task.get("target_program_id") != "workflow_auto_sync"
                or task.get("status") != "QUEUED"
                or task.get("lease") is not None
                or task.get("dispatch_intent") is not None
                or not isinstance(task.get("input"), dict)
                or task["input"].get("production_decision") not in {
                    "INPUT_CHANGED", "SCHEDULE_DUE", "RECOVERY_REQUIRED", "USER_AUTHORIZED_MANUAL_AUDIT"
                }
                or task["input"].get("production_fingerprint") != current_fingerprint):
            continue
        not_before = task.get("not_before")
        if not_before:
            try:
                retry_at = datetime.fromisoformat(str(not_before).replace("Z", "+00:00"))
            except ValueError:
                continue
            # A retry is not dispatchable until its durable backoff expires.
            # Treat malformed/naive timestamps as unsafe and leave the task queued.
            if retry_at.tzinfo is None or retry_at.astimezone(timezone.utc) > now:
                continue
        candidates.append(task)
    if not candidates:
        return ""
    selected = min(
        candidates,
        key=lambda task: (
            -int(task.get("priority", 0) or 0),
            str(task.get("created_at") or ""),
            str(task.get("task_id") or ""),
        ),
    )
    task_id = selected.get("task_id")
    return task_id if isinstance(task_id, str) and task_id else ""

