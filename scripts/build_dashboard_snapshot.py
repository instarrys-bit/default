#!/usr/bin/env python3
"""Build a sanitized, read-only GitHub Pages operations snapshot."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "data.json"

def read_json(path):
    try:
        with (ROOT / path).open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

def as_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else 0

manifest = read_json("rulesets/manifest.json")
queue_doc = read_json("automation/task_queue.json")
pending = read_json("rulesets/pending_queue.json")
lifecycle = read_json("rulesets/lifecycle_state.json")
lifecycle_report = read_json("reports/lifecycle/latest.json")
candidates = read_json("data/candidates.json")

tasks = queue_doc.get("tasks", []) if isinstance(queue_doc.get("tasks"), list) else []
queue_status = {}
for task in tasks:
    status = str(task.get("status", "UNKNOWN")).upper()
    queue_status[status] = queue_status.get(status, 0) + 1

production_tasks = [t for t in tasks if t.get("target_program_id") == "workflow_auto_sync"]
prod_status = {}
for task in production_tasks:
    status = str(task.get("status", "UNKNOWN")).upper()
    prod_status[status] = prod_status.get(status, 0) + 1

successful = [t for t in production_tasks
              if str(t.get("status", "")).upper() == "SUCCEEDED"
              and (t.get("verification") or {}).get("status") == "passed"
              and (t.get("verification") or {}).get("verified_at")]
successful.sort(key=lambda t: str((t.get("verification") or {}).get("verified_at", "")))
last_verified = (successful[-1].get("verification") or {}).get("verified_at") if successful else None
next_expected = None
if last_verified:
    try:
        parsed = datetime.fromisoformat(last_verified.replace("Z", "+00:00"))
        next_expected = (parsed + timedelta(days=8)).astimezone(timezone.utc).isoformat()
    except ValueError:
        pass

counts = manifest.get("rule_count", {}) if isinstance(manifest.get("rule_count"), dict) else {}
published = as_int(manifest.get("published_rule_total"))
max_published = as_int(manifest.get("max_published_rules"))
reviewed = as_int(manifest.get("reviewed_total"))
approved = as_int(manifest.get("approved_total"))
held = as_int(manifest.get("held_total"))
candidate_count = as_int(candidates.get("candidate_count"))
source_count = as_int(manifest.get("source_count"))

snapshot = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "source_commit": os.environ.get("GITHUB_SHA", "local"),
    "sources": {"source_count": source_count, "candidate_count": candidate_count},
    "rulesets": {
        "by_policy": {p: as_int(counts.get(p)) for p in ("DIRECT", "PROXY", "REJECT")},
        "published_total": published,
        "max_published": max_published,
        "queued_total": as_int(manifest.get("queued_rule_total", pending.get("queued_count", 0)))
    },
    "review": {
        "reviewed_total": reviewed,
        "approved_total": approved,
        "held_total": held,
        "policy_conflicts": as_int(manifest.get("policy_conflict_total")),
        "reject_manual_approval_required": bool(manifest.get("reject_manual_approval_required", True)),
        "reject_manual_approved": as_int(manifest.get("reject_manual_approval_count"))
    },
    "queue": {"total": len(tasks), "by_status": queue_status},
    "production": {
        "total_tasks": len(production_tasks),
        "succeeded": prod_status.get("SUCCEEDED", 0),
        "active": sum(prod_status.get(s, 0) for s in ("QUEUED", "CLAIMED", "VERIFYING")),
        "dead_letter": prod_status.get("DEAD_LETTER", 0),
        "last_success_verified_at": last_verified,
        "next_expected_at": next_expected
    },
    "lifecycle": {
        "published_rule_count": as_int(lifecycle.get("published_rule_count", lifecycle_report.get("published_rule_count"))),
        "next_milestone": as_int(lifecycle.get("next_milestone", lifecycle_report.get("next_milestone"))),
        "max_published_rules": as_int(lifecycle.get("max_published_rules", lifecycle_report.get("max_published_rules"))),
        "status": str(lifecycle.get("status", "unknown")),
        "latest_review_status": str(lifecycle_report.get("status", "no_record")),
        "last_successful_review_at": lifecycle.get("last_successful_review_at")
    }
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("dashboard snapshot generated")
