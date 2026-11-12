#!/usr/bin/env python3
"""Build a sanitized, read-only GitHub Pages operations snapshot."""

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from json_document_store import read_document, iter_document_records
from remote_task_queue_runtime import make_store

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


def watchdog_schedule(workflow_text, now=None):
    """Return the next UTC workflow trigger; unknown cron forms fail closed."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("watchdog schedule clock must be timezone-aware")
    now = now.astimezone(timezone.utc)
    expressions = []
    for line in workflow_text.splitlines():
        item = line.strip()
        if item.startswith("- cron:"):
            expression = item[len("- cron:"):].strip().strip("\"'")
            if expression:
                expressions.append(expression)
    if not expressions:
        return {"cron": [], "next_scheduled_trigger_at": None, "schedule_state": "unavailable"}
    candidates = []
    for expression in expressions:
        if expression == "*/15 * * * *":
            next_minute = ((now.minute // 15) + 1) * 15
            candidate = now.replace(second=0, microsecond=0)
            if next_minute >= 60:
                candidate = candidate.replace(minute=0) + timedelta(hours=1)
            else:
                candidate = candidate.replace(minute=next_minute)
            candidates.append(candidate)
        elif expression == "0 * * * *":
            candidates.append(now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
        elif expression == "30 22 * * *":
            candidate = now.replace(hour=22, minute=30, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            candidates.append(candidate)
        else:
            return {"cron": expressions, "next_scheduled_trigger_at": None, "schedule_state": "unsupported_cron"}
    return {"cron": expressions, "next_scheduled_trigger_at": min(candidates).isoformat(), "schedule_state": "known"}


def build_dead_letter_metrics(tasks):
    """Separate historical workflow cancellations from actual exhausted failures."""
    failures = cancelled = unclassified = 0
    for task in tasks:
        if not isinstance(task, dict) or str(task.get("status", "")).upper() != "DEAD_LETTER":
            continue
        error = task.get("last_error")
        evidence = error.get("evidence") if isinstance(error, dict) else None
        conclusion = evidence.get("conclusion") if isinstance(evidence, dict) else None
        if conclusion == "cancelled":
            cancelled += 1
        elif conclusion in {"failure", "timed_out", "startup_failure"}:
            failures += 1
        else:
            unclassified += 1
    return {
        "dead_letter_failures": failures,
        "dead_letter_cancelled": cancelled,
        "dead_letter_unclassified": unclassified,
    }


def build_manual_review_metrics(tasks):
    """Only exhausted runtime failures enter human review; cancellations do not."""
    metrics = build_dead_letter_metrics(tasks)
    return {
        "pending": metrics["dead_letter_failures"] + metrics["dead_letter_unclassified"],
        "failures": metrics["dead_letter_failures"],
        "unclassified": metrics["dead_letter_unclassified"],
        "cancelled_excluded": metrics["dead_letter_cancelled"],
    }


def build_source_pipeline_metrics(discovered, assessments, candidates, registry):
    """Keep active sources distinct from discovered and assessed source candidates."""
    discovered_rows = discovered.get("candidates", [])
    assessment_rows = assessments.get("assessments", [])
    candidate_rows = candidates.get("candidates", [])
    repositories = registry.get("repositories", [])
    source_files = registry.get("source_files", [])
    return {
        "discovered_repository_count": as_int(discovered.get("candidate_count")) or (
            len(discovered_rows) if isinstance(discovered_rows, list) else 0
        ),
        "assessed_file_count": len(assessment_rows) if isinstance(assessment_rows, list) else 0,
        "source_candidate_count": as_int(candidates.get("candidate_count")) or (
            len(candidate_rows) if isinstance(candidate_rows, list) else 0
        ),
        "eligible_candidate_count": as_int(candidates.get("eligible_candidate_count")),
        "durable_repository_count": as_int(registry.get("repository_count")) or (
            len(repositories) if isinstance(repositories, list) else 0
        ),
        "durable_source_file_count": as_int(registry.get("source_file_count")) or (
            len(source_files) if isinstance(source_files, list) else 0
        ),
        "pending_assessment_count": as_int(registry.get("pending_assessment_count")),
        "registry_published": bool(registry),
    }


def build_task_stage_metrics(tasks, target_program_id):
    selected = [
        task for task in tasks
        if isinstance(task, dict) and task.get("target_program_id") == target_program_id
    ]
    status_counts = {}
    for task in selected:
        status = str(task.get("status", "UNKNOWN")).upper()
        status_counts[status] = status_counts.get(status, 0) + 1
    timestamps = [
        task.get("updated_at") or task.get("created_at")
        for task in selected
        if isinstance(task.get("updated_at") or task.get("created_at"), str)
    ]
    return {
        "total": len(selected),
        "by_status": status_counts,
        "last_task_at": max(timestamps) if timestamps else None,
    }


 
def build_combined_task_runtime_metrics(tasks, target_program_ids):
    """Aggregate production, Discovery and Assessment task lanes."""
    targets = set(target_program_ids)
    selected = [
        task for task in tasks
        if isinstance(task, dict) and task.get("target_program_id") in targets
    ]
    by_status = {}
    for task in selected:
        status = str(task.get("status", "UNKNOWN")).upper()
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "total": len(selected),
        "by_status": by_status,
        "active": sum(by_status.get(status, 0) for status in ("QUEUED", "CLAIMED", "VERIFYING")),
        "succeeded": by_status.get("SUCCEEDED", 0),
        "dead_letter": by_status.get("DEAD_LETTER", 0),
        "cancelled": by_status.get("CANCELLED", 0),
    }


def build_candidate_review_metrics(candidates, review_records, cursor=None, ledger_updated_at=None):
    candidate_domains = {
        str(item.get("domain", "")).lower().rstrip(".")
        for item in candidates
        if isinstance(item, dict) and item.get("domain")
    }
    review_by_domain = {
        str(item.get("domain", "")).lower().rstrip("."): item
        for item in review_records
        if isinstance(item, dict) and item.get("domain")
    }
    status_counts = {}
    for domain in candidate_domains:
        record = review_by_domain.get(domain)
        status = str(record.get("status", "UNKNOWN")).upper() if record else "UNREVIEWED"
        status_counts[status] = status_counts.get(status, 0) + 1
    cursor = cursor if isinstance(cursor, dict) else {}
    recorded = sum(1 for domain in candidate_domains if domain in review_by_domain)
    return {
        "candidate_total": len(candidate_domains),
        "history_recorded": recorded,
        "missing_history": len(candidate_domains) - recorded,
        "status_counts": status_counts,
        "review_ledger_total": len(review_records),
        "review_ledger_updated_at": ledger_updated_at,
        "cursor_status": str(cursor.get("status", "unknown")),
        "cursor_candidate_count": cursor.get("candidate_count", 0)
        if isinstance(cursor.get("candidate_count", 0), int) else 0,
    }

def main():
    manifest = read_json("rulesets/manifest.json")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN", "")
    if repository and token:
        queue_doc = make_store(repository=repository, token=token).read().document
    else:
        # Local development only: the repository snapshot is a read-only bootstrap.
        queue_doc = read_json("automation/task_queue.json")
    production_control = read_json("automation/production_control.json")
    pending = read_json("rulesets/pending_queue.json")
    lifecycle = read_json("rulesets/lifecycle_state.json")
    lifecycle_report = read_json("reports/lifecycle/latest.json")
    candidates_doc = read_document(ROOT / "data" / "candidates.json", "candidates", {"candidates": [], "sources": []})
    candidates = candidates_doc.get("candidates", []) if isinstance(candidates_doc.get("candidates"), list) else []
    review_records = list(iter_document_records(ROOT / "sources" / "domain_reviews.json", "reviews"))
    review_cursor = read_json("sources/review_cursor.json")
    review_ledger_manifest = read_json("sources/domain_reviews.json.manifest.json")
    review_ledger_updated_at = ((review_ledger_manifest.get("metadata") or {}).get("updated_at")
                                or read_json("sources/domain_reviews.json").get("updated_at"))
    candidate_review = build_candidate_review_metrics(
        candidates, review_records, review_cursor, review_ledger_updated_at
    )
    discovered_sources = read_document(ROOT / "sources" / "discovered_sources.json", "candidates", {"candidates": []})
    source_assessments = read_document(ROOT / "sources" / "source_assessments.json", "assessments", {"assessments": []})
    source_candidates = read_json("sources/source_candidates.json")
    durable_source_registry = read_json("rulesets/source_candidate_registry.json")
    source_pipeline = build_source_pipeline_metrics(
        discovered_sources, source_assessments, source_candidates, durable_source_registry
    )
    
    tasks = queue_doc.get("tasks", []) if isinstance(queue_doc.get("tasks"), list) else []
    queue_status = {}
    for task in tasks:
        status = str(task.get("status", "UNKNOWN")).upper()
        queue_status[status] = queue_status.get(status, 0) + 1
    
    discovery_metrics = build_task_stage_metrics(tasks, "workflow_source_discovery")
    assessment_metrics = build_task_stage_metrics(tasks, "script_assess_sources")
    production_tasks = [t for t in tasks if t.get("target_program_id") == "workflow_auto_sync"]
    combined_task_runtime = build_combined_task_runtime_metrics(
        tasks, ("workflow_auto_sync", "workflow_source_discovery", "script_assess_sources")
    )
    prod_status = {}
    for task in production_tasks:
        status = str(task.get("status", "UNKNOWN")).upper()
        prod_status[status] = prod_status.get(status, 0) + 1
    dead_letter_metrics = build_dead_letter_metrics(production_tasks)
    manual_review_metrics = build_manual_review_metrics(tasks)
    
    successful = [t for t in production_tasks
                  if str(t.get("status", "")).upper() == "SUCCEEDED"
                  and (t.get("verification") or {}).get("status") == "passed"
                  and (t.get("verification") or {}).get("verified_at")]
    successful.sort(key=lambda t: str((t.get("verification") or {}).get("verified_at", "")))
    last_verified = (successful[-1].get("verification") or {}).get("verified_at") if successful else None
    counts = manifest.get("rule_count", {}) if isinstance(manifest.get("rule_count"), dict) else {}
    published = as_int(manifest.get("published_rule_total"))
    max_published = as_int(manifest.get("max_published_rules"))
    reviewed = as_int(manifest.get("reviewed_total"))
    approved = as_int(manifest.get("approved_total"))
    held = as_int(manifest.get("held_total"))
    candidate_count = candidate_review["candidate_total"]
    source_count = as_int(manifest.get("source_count"))
    
    def watchdog_status():
        workflow_path = ROOT / ".github" / "workflows" / "automation-watchdog.yml"
        try:
            schedule = watchdog_schedule(workflow_path.read_text(encoding="utf-8"))
        except OSError as exc:
            print("watchdog schedule unavailable: " + str(exc))
            schedule = {"cron": [], "next_scheduled_trigger_at": None, "schedule_state": "unavailable"}
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        # The workflow exposes github.token as GITHUB_TOKEN. Accept both names
        # so dashboard diagnostics do not silently degrade to "unknown".
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
        if not repo or not token:
            return {"workflow_state": "unknown", "last_run_status": "unknown",
                    "last_run_conclusion": None, "last_run_at": None, **schedule}
        headers = {"Accept": "application/vnd.github+json",
                   "Authorization": "Bearer " + token,
                   "X-GitHub-Api-Version": "2022-11-28"}
        def api(path):
            request = urllib.request.Request(
                "https://api.github.com/repos/" + repo + path, headers=headers)
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.load(response)
        try:
            workflow = api("/actions/workflows/automation-watchdog.yml")
            runs = api("/actions/workflows/automation-watchdog.yml/runs?per_page=1")
            latest = (runs.get("workflow_runs") or [{}])[0]
            return {"workflow_state": workflow.get("state", "unknown"),
                    "last_run_status": latest.get("status", "unknown"),
                    "last_run_conclusion": latest.get("conclusion"),
                    "last_run_at": latest.get("run_started_at") or latest.get("created_at"),
                    **schedule}
        except Exception as exc:
            print("watchdog status unavailable: " + str(exc))
            return {"workflow_state": "unknown", "last_run_status": "unknown",
                    "last_run_conclusion": None, "last_run_at": None, **schedule}

    
    snapshot = {
        "schema_version": 1,
        "automation": watchdog_status(),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_commit": os.environ.get("GITHUB_SHA", "local"),
        "sources": {
            "source_count": source_count,
            "candidate_count": candidate_count,
            **source_pipeline,
        },
        "candidate_review": candidate_review,
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
            "manual_review_scope": "runtime_exceptions_only",
            "manual_review_pending": manual_review_metrics["pending"],
            "manual_review_failures": manual_review_metrics["failures"],
            "manual_review_unclassified": manual_review_metrics["unclassified"],
            "manual_review_cancelled_excluded": manual_review_metrics["cancelled_excluded"]
        },
        "queue": {"total": len(tasks), "by_status": queue_status},
        "pipeline": {
            "source_discovery": discovery_metrics,
            "source_assessment": assessment_metrics,
            "task_runtime": combined_task_runtime,
            "ruleset_production": {
                "total": len(production_tasks),
                "by_status": prod_status,
            }
        },
        "production": {
            "dispatch_mode": production_control.get("dispatch_mode") if production_control.get("dispatch_mode") in ("enabled", "hold") else "unknown",
            "dispatch_updated_at": production_control.get("updated_at") if isinstance(production_control.get("updated_at"), str) else None,
            "total_tasks": len(production_tasks),
            "succeeded": prod_status.get("SUCCEEDED", 0),
            "active": sum(prod_status.get(s, 0) for s in ("QUEUED", "CLAIMED", "VERIFYING")),
            "dead_letter": prod_status.get("DEAD_LETTER", 0),
            "dead_letter_failures": dead_letter_metrics["dead_letter_failures"],
            "dead_letter_cancelled": dead_letter_metrics["dead_letter_cancelled"],
            "dead_letter_unclassified": dead_letter_metrics["dead_letter_unclassified"],
            "cancelled_total": prod_status.get("CANCELLED", 0) + dead_letter_metrics["dead_letter_cancelled"],
            "last_success_verified_at": last_verified,
            "next_task_eligible_at": None,
            "task_eligibility_state": "conditional_unknown",
            "task_eligibility_note": "A scheduled workflow trigger does not guarantee production dispatch; Watchdog evaluates input fingerprints, queue state, leases, and the production hold control."
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


if __name__ == "__main__":
    main()
