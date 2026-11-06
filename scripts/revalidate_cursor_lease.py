#!/usr/bin/env python3
"""Revalidate exact Watchdog task and install live resource fence for cursor persist."""
import json, os, re
from datetime import datetime, timezone
from pathlib import Path
correlation = os.environ.get("AUTOMATION_TASK_CORRELATION", "")
match = re.fullmatch(r"(task_[0-9a-f]{24})-a([1-9][0-9]*)", correlation)
if not match:
    raise SystemExit("A valid Watchdog task correlation is required for cursor persistence.")
task_id, attempt_text = match.groups()
attempt = int(attempt_text)
queue = json.loads(Path("automation/task_queue.json").read_text(encoding="utf-8"))
task = next((x for x in queue.get("tasks", []) if isinstance(x, dict) and x.get("task_id") == task_id), None)
if not isinstance(task, dict):
    raise SystemExit("The canonical Watchdog task is absent from the durable queue.")
intent = task.get("dispatch_intent")
if (task.get("target_program_id") != "workflow_auto_sync"
        or task.get("requester_program_id") != "workflow_automation_watchdog"
        or task.get("attempts") != attempt
        or task.get("status") not in {"CLAIMED", "VERIFYING"}
        or not isinstance(intent, dict)
        or intent.get("task_id") != task_id
        or intent.get("dispatch_attempt") != attempt
        or intent.get("correlation_id") != correlation
        or intent.get("workflow_path") != ".github/workflows/auto_sync.yml"
        or intent.get("ref") != "main"):
    raise SystemExit("The durable queue does not authorize this exact failed-run cursor writer.")
try:
    proof = json.loads(os.environ["RESOURCE_LEASE_PROOF"])
except json.JSONDecodeError as exc:
    raise SystemExit("The resource lease proof is invalid JSON.") from exc
resource_lease = task.get("resource_lease")
declared = resource_lease.get("resources") if isinstance(resource_lease, dict) else None
queue_leases = queue.get("resource_leases")
if (not isinstance(resource_lease, dict) or resource_lease.get("status") != "ACTIVE"
        or not isinstance(declared, dict) or proof != declared
        or not isinstance(queue_leases, dict) or "sources/review_cursor.json" not in proof):
    raise SystemExit("The review cursor resource lease is missing, inactive or inconsistent.")
workers = set()
now = datetime.now(timezone.utc)
for key, item in proof.items():
    record = queue_leases.get(key)
    if (not isinstance(record, dict) or record.get("status") != "ACTIVE"
            or record.get("task_id") != task_id
            or record.get("lease_id") != item.get("lease_id")
            or record.get("fencing_token") != item.get("fencing_token")):
        raise SystemExit("A cursor writer resource lease is stale or fenced: " + key)
    if datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= now:
        raise SystemExit("A cursor writer resource lease has expired: " + key)
    workers.add(record.get("worker_id"))
if len(workers) != 1 or not next(iter(workers)):
    raise SystemExit("Cursor writer resources do not share one active worker owner.")
lease = task.get("lease")
if task.get("status") == "CLAIMED" and (not isinstance(lease, dict) or not lease.get("token")):
    raise SystemExit("A CLAIMED task must retain its scheduler task lease.")
env_values = {
    "AUTOMATION_TASK_ID": task_id,
    "AUTOMATION_TASK_ID_BASE": task_id,
    "AUTOMATION_WORKER_ID": next(iter(workers)),
    "AUTOMATION_TASK_LEASE_TOKEN": lease.get("token") if isinstance(lease, dict) else "resource-fence-only",
    "AUTOMATION_QUEUE_REPOSITORY": os.environ["GITHUB_REPOSITORY"],
    "AUTOMATION_QUEUE_BRANCH": "main",
    "AUTOMATION_QUEUE_PATH": "automation/task_queue.json",
    "AUTOMATION_QUEUE_TOKEN": os.environ["GH_TOKEN"],
    "AUTOMATION_QUEUE_SNAPSHOT": str(Path("automation/task_queue.json").resolve()),
}
delimiter = "__CURSOR_RESOURCE_PROOF__"
if delimiter in os.environ["RESOURCE_LEASE_PROOF"]:
    raise SystemExit("Invalid cursor resource proof delimiter.")
with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
    for key, value in env_values.items():
        stream.write(f"{key}={value}\n")
    stream.write(f"AUTOMATION_RESOURCE_LEASE_PROOF<<{delimiter}\n{os.environ['RESOURCE_LEASE_PROOF']}\n{delimiter}\n")
