#!/usr/bin/env python3
"""Verify Watchdog-owned durable task dispatch (extracted from auto_sync audit job)."""
import json
import os
import re
from pathlib import Path

correlation = os.environ.get("AUTOMATION_TASK_ID", "")
match = re.fullmatch(r"(task_[0-9a-f]{24})-a([1-9][0-9]*)", correlation)
if not match:
    raise SystemExit("A valid Watchdog task correlation is required; direct/manual audit dispatch is not authorized.")

task_id, attempt_text = match.groups()
attempt = int(attempt_text)
queue = json.loads(Path("automation/task_queue.json").read_text(encoding="utf-8"))
task = next((item for item in queue.get("tasks", []) if item.get("task_id") == task_id), None)
if task is None:
    raise SystemExit("The correlated durable task does not exist in the checked-out queue snapshot.")
lease = task.get("lease")
resource_lease = task.get("resource_lease")
proof_text = os.environ.get("RESOURCE_LEASE_PROOF", "")
try:
    proof = json.loads(proof_text)
except json.JSONDecodeError as exc:
    raise SystemExit("The Watchdog resource lease proof is not valid JSON.") from exc
declared = resource_lease.get("resources") if isinstance(resource_lease, dict) else None
queue_leases = queue.get("resource_leases")
if (task.get("status") not in {"CLAIMED", "VERIFYING"}
        or not isinstance(resource_lease, dict) or resource_lease.get("status") != "ACTIVE"
        or not isinstance(declared, dict) or proof != declared
        or not isinstance(queue_leases, dict) or not isinstance(proof, dict) or not proof):
    raise SystemExit("The Watchdog resource lease proof is missing, inactive or inconsistent.")
workers = set()
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
for key, item in proof.items():
    record = queue_leases.get(key)
    if (not isinstance(record, dict) or record.get("status") != "ACTIVE"
            or record.get("task_id") != task_id
            or record.get("lease_id") != item.get("lease_id")
            or record.get("fencing_token") != item.get("fencing_token")):
        raise SystemExit("The Watchdog resource lease is stale or fenced: " + key)
    expiry = datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00"))
    if expiry <= now:
        raise SystemExit("The Watchdog resource lease has expired: " + key)
    workers.add(record.get("worker_id"))
if len(workers) != 1 or not next(iter(workers)):
    raise SystemExit("The Watchdog resource leases do not share one active worker owner.")
worker_id = next(iter(workers))
if task.get("status") == "CLAIMED" and (
        not isinstance(lease, dict) or not lease.get("owner") or not lease.get("token")):
    raise SystemExit("A CLAIMED task must retain its scheduler task lease.")
task_lease_token = lease.get("token") if isinstance(lease, dict) else "resource-fence-only"
env_values = {
    "AUTOMATION_TASK_ID": task_id,
    "AUTOMATION_WORKER_ID": worker_id,
    "AUTOMATION_TASK_LEASE_TOKEN": task_lease_token,
    "AUTOMATION_QUEUE_REPOSITORY": os.environ["GITHUB_REPOSITORY"],
    "AUTOMATION_QUEUE_BRANCH": "main",
    "AUTOMATION_QUEUE_PATH": "automation/task_queue.json",
    "AUTOMATION_QUEUE_TOKEN": os.environ["GH_TOKEN"],
    "AUTOMATION_QUEUE_SNAPSHOT": str(Path("automation/task_queue.json").resolve()),
}
delimiter = "__WATCHDOG_RESOURCE_PROOF__"
if delimiter in proof_text:
    raise SystemExit("The resource proof contains an invalid environment delimiter.")
with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
    stream.write(f"AUTOMATION_TASK_ID_BASE={task_id}\n")
    for key, value in env_values.items():
        stream.write(f"{key}={value}\n")
    stream.write(f"AUTOMATION_RESOURCE_LEASE_PROOF<<{delimiter}\n{proof_text}\n{delimiter}\n")

intent = task.get("dispatch_intent")
if (
    task.get("target_program_id") != "workflow_auto_sync"
    or task.get("requester_program_id") != "workflow_automation_watchdog"
    or task.get("attempts") != attempt
    or not isinstance(intent, dict)
    or intent.get("task_id") != task_id
    or intent.get("correlation_id") != correlation
    or intent.get("dispatch_attempt") != attempt
    or intent.get("workflow_path") != ".github/workflows/auto_sync.yml"
    or intent.get("ref") != "main"
):
    raise SystemExit("The queue record does not authorize this exact Watchdog production audit dispatch.")

production_fingerprint = os.environ.get("PRODUCTION_FINGERPRINT", "")
production_decision = os.environ.get("PRODUCTION_DECISION", "")
production_reason = os.environ.get("PRODUCTION_REASON", "")
if production_fingerprint:
    task_input = task.get("input")
    if (
        not isinstance(task_input, dict)
        or task_input.get("production_fingerprint") != production_fingerprint
        or task_input.get("production_decision") != production_decision
        or task_input.get("production_reason") != production_reason
        or production_decision not in {"INPUT_CHANGED", "SCHEDULE_DUE", "RECOVERY_REQUIRED"}
        or not production_reason
    ):
        raise SystemExit("The dispatched production intent does not match the durable task input.")
task_input = task.get("input")
if not isinstance(task_input, dict):
    raise SystemExit("The durable task input is missing or invalid.")
for field, env_name in (
    ("baseline_source_event", "BASELINE_SOURCE_EVENT"),
    ("baseline_source_actor", "BASELINE_SOURCE_ACTOR"),
    ("baseline_source_before", "BASELINE_SOURCE_BEFORE"),
    ("baseline_source_sha", "BASELINE_SOURCE_SHA"),
):
    supplied = os.environ.get(env_name, "")
    durable_value = task_input.get(field, "")
    if durable_value != supplied:
        raise SystemExit(f"Dispatched {field} does not match the durable Watchdog task input.")
baseline_sha = os.environ.get("BASELINE_SOURCE_SHA", "")
if baseline_sha and not re.fullmatch(r"[0-9a-f]{40}", baseline_sha):
    raise SystemExit("The dispatched baseline source SHA is not a full Git commit SHA.")
if task.get("status") == "VERIFYING":
    result = task.get("result")
    if (
        not isinstance(result, dict)
        or result.get("correlation_id") != correlation
        or result.get("dispatch_state") != "submitted"
    ):
        raise SystemExit("The VERIFYING task has no matching persisted dispatch submission.")

print(f"Authorized Watchdog production audit task {task_id}, attempt {attempt}.")
