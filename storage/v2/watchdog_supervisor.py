"""Read-only V2 Watchdog supervisor and fenced recovery planner."""
from __future__ import annotations
import argparse, json, os
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def _parse_time(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("observed_at must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must include a timezone")
    return parsed

def plan_recovery(state: dict | None, *, observed_at: str) -> dict:
    """Plan expired-lease recovery in safe event order without mutating state."""
    now = _parse_time(observed_at)
    if state is None:
        return {
            "schema_version": 1, "planner": "watchdog-v2-read-only/1",
            "status": "NOT_INITIALIZED", "observed_at": observed_at,
            "expected_revision": None, "actions": [], "dispatch_enabled": False,
            "dispatch_block_reason": "V2 task routing and Storage Manager apply/dispatch interfaces are not enabled.",
        }
    from runtime import project
    projection = project(state)
    tasks, resources = projection["tasks"], projection["resource_leases"]
    actions, planned_resource_expiry, planned_task_expiry = [], set(), set()
    revision = state["revision"]
    for key, lease in sorted(resources.items()):
        if lease.get("status") != "ACTIVE" or now < _parse_time(lease["expires_at"]):
            continue
        planned_resource_expiry.add(key)
        actions.append({
            "event_type": "RESOURCE_LEASE_EXPIRED", "resource_key": key,
            "lease_id": lease["lease_id"], "fencing_token": lease["fencing_token"],
            "idempotency_key": "watchdog-v2:resource-expire:" + key + ":" + lease["lease_id"],
            "expected_revision": revision + len(actions), "apply_via": "storage_management",
        })
    for task_id, task in sorted(tasks.items()):
        lease = task.get("task_lease") or {}
        if lease.get("status") != "ACTIVE" or now < _parse_time(lease["expires_at"]):
            continue
        planned_task_expiry.add(task_id)
        actions.append({
            "event_type": "TASK_LEASE_EXPIRED", "task_id": task_id,
            "lease_id": lease["lease_id"], "owner": lease["owner"],
            "idempotency_key": "watchdog-v2:task-expire:" + task_id + ":" + lease["lease_id"],
            "expected_revision": revision + len(actions), "apply_via": "storage_management",
            "lease_token_in_state_only": True,
        })
    for task_id, task in sorted(tasks.items()):
        if task.get("status") not in {"CLAIMED", "RUNNING"}:
            continue
        lease = task.get("task_lease") or {}
        if lease.get("status") != "EXPIRED" and task_id not in planned_task_expiry:
            continue
        active_resources = [
            key for key, resource in resources.items()
            if resource.get("status") == "ACTIVE"
            and resource.get("task_id") == task_id
            and key not in planned_resource_expiry
        ]
        if active_resources:
            continue
        if task["attempts"] >= task["max_attempts"]:
            actions.append({
                "event_type": "TASK_DEAD_LETTER", "task_id": task_id,
                "reason": "task lease expired and retry budget exhausted",
                "idempotency_key": "watchdog-v2:dead-letter:" + task_id + ":" + lease.get("lease_id", ""),
                "expected_revision": revision + len(actions), "apply_via": "storage_management",
            })
        else:
            actions.append({
                "event_type": "TASK_REQUEUED", "task_id": task_id,
                "lease_id": lease.get("lease_id"), "owner": lease.get("owner"),
                "reason": "task lease expired; all resource leases are released or expired",
                "idempotency_key": "watchdog-v2:requeue:" + task_id + ":" + lease.get("lease_id", ""),
                "expected_revision": revision + len(actions), "apply_via": "storage_management",
                "lease_token_in_state_only": True,
            })
    return {
        "schema_version": 1, "planner": "watchdog-v2-read-only/1",
        "status": "RECOVERY_ACTIONS_PENDING" if actions else "NO_ACTIONS",
        "observed_at": observed_at, "epoch_id": state["epoch_id"],
        "expected_revision": revision, "event_count": len(state["events"]),
        "task_status_counts": projection["status_counts"],
        "resource_status_counts": dict(Counter(x.get("status", "UNKNOWN") for x in resources.values())),
        "actions": actions, "action_count": len(actions), "dispatch_enabled": False,
        "dispatch_block_reason": "V2 task routing and Storage Manager apply/dispatch interfaces are not enabled.",
        "secret_handling": "Opaque task lease tokens are never emitted; Storage Management must rehydrate them from the current state after CAS revision validation.",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--observed-at", default=None)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not args.repository or not token:
        raise SystemExit("V2 Watchdog supervisor requires repository and read-only GITHUB_TOKEN")
    observed_at = args.observed_at or datetime.now().astimezone().isoformat()
    from runtime import GitHubContentsBackend
    state, _ = GitHubContentsBackend(args.repository, args.branch, token).read()
    plan = plan_recovery(state, observed_at=observed_at)
    rendered = json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2)
    print(rendered)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## V2 Watchdog read-only supervisor\n\n")
            stream.write(f"- Status: {plan['status']}\n")
            stream.write(f"- Planned recovery actions: {plan.get('action_count', 0)}\n")
            stream.write("- Worker dispatch: disabled\n")
            stream.write("- State writes: none; Storage Management remains the sole writer.\n\n")
            stream.write("JSON plan:\n" + rendered + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
