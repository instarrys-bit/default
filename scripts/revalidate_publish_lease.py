#!/usr/bin/env python3
"""Revalidate Watchdog task and export canonical lease context for publish."""
import json, os, re
from pathlib import Path
correlation = os.environ.get("AUTOMATION_TASK_ID", "")
match = re.fullmatch(r"(task_[0-9a-f]{24})-a([1-9][0-9]*)", correlation)
if not match:
    raise SystemExit("Publish requires a canonical Watchdog task correlation.")
task_id, attempt_text = match.groups()
attempt = int(attempt_text)
queue = json.loads(Path("automation/task_queue.json").read_text(encoding="utf-8"))
task = next((x for x in queue.get("tasks", []) if isinstance(x, dict) and x.get("task_id") == task_id), None)
proof_text = os.environ.get("RESOURCE_LEASE_PROOF", "")
try:
    proof = json.loads(proof_text)
except json.JSONDecodeError as exc:
    raise SystemExit("Publish resource lease proof is invalid JSON.") from exc
lease = task.get("lease") if isinstance(task, dict) else None
intent = task.get("dispatch_intent") if isinstance(task, dict) else None
if (not isinstance(task, dict) or task.get("target_program_id") != "workflow_auto_sync"
        or task.get("requester_program_id") != "workflow_automation_watchdog"
        or task.get("attempts") != attempt or not isinstance(intent, dict)
        or intent.get("task_id") != task_id or intent.get("dispatch_attempt") != attempt
        or intent.get("correlation_id") != correlation
        or intent.get("workflow_path") != ".github/workflows/auto_sync.yml"
        or intent.get("ref") != "main"
        or not isinstance(lease, dict) or not lease.get("owner") or not lease.get("token")
        or not isinstance(proof, dict) or not proof):
    raise SystemExit("The current queue record does not authorize this exact publish attempt.")
values = {
    "AUTOMATION_TASK_ID_BASE": task_id,
    "AUTOMATION_TASK_ID": task_id,
    "AUTOMATION_WORKER_ID": lease["owner"],
    "AUTOMATION_TASK_LEASE_TOKEN": lease["token"],
    "AUTOMATION_QUEUE_REPOSITORY": os.environ["GITHUB_REPOSITORY"],
    "AUTOMATION_QUEUE_BRANCH": "main",
    "AUTOMATION_QUEUE_PATH": "automation/task_queue.json",
    "AUTOMATION_QUEUE_TOKEN": os.environ["GH_TOKEN"],
    "AUTOMATION_QUEUE_SNAPSHOT": str(Path("automation/task_queue.json").resolve()),
}
with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as stream:
    for key, value in values.items():
        stream.write(f"{key}={value}\n")
    delimiter = "__PUBLISH_RESOURCE_PROOF__"
    if delimiter in proof_text:
        raise SystemExit("Invalid publish proof delimiter.")
    stream.write(f"AUTOMATION_RESOURCE_LEASE_PROOF<<{delimiter}\n{proof_text}\n{delimiter}\n")
