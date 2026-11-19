"""Build a sanitized, read-only V2 dashboard snapshot from Storage Management."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DEFAULT = ROOT / "dashboard" / "v2" / "data.json"


def build_snapshot(state: dict | None, migration_manifest: dict, inventory: dict) -> dict:
    from runtime import project

    if state is None:
        projection = {"tasks": {}, "resource_leases": {}, "status_counts": {}}
        epoch_status = "NOT_INITIALIZED"
        revision = None
        events = []
        epoch_id = None
    else:
        projection = project(state)
        epoch_status = "INITIALIZED"
        revision = state["revision"]
        events = state["events"]
        epoch_id = state["epoch_id"]

    tasks = projection["tasks"]
    resources = projection["resource_leases"]
    task_rows = [{
        "task_id": task_id,
        "status": task.get("status"),
        "attempts": task.get("attempts"),
        "max_attempts": task.get("max_attempts"),
        "created_at": task.get("created_at"),
        "result_artifact_id": task.get("result_artifact_id"),
    } for task_id, task in sorted(tasks.items(), key=lambda item: item[1].get("created_at", ""), reverse=True)[:50]]
    resource_rows = [{
        "resource_key": key,
        "status": lease.get("status"),
        "task_id": lease.get("task_id"),
        "owner": lease.get("owner"),
        "fencing_token": lease.get("fencing_token"),
        "expires_at": lease.get("expires_at"),
    } for key, lease in sorted(resources.items())]

    migration_entries = migration_manifest.get("entries", [])
    migration_status_counts = dict(Counter(
        entry.get("migration_status", "UNKNOWN")
        for entry in migration_entries if isinstance(entry, dict)
    ))
    promotion_status_counts = dict(Counter(
        entry.get("promotion_status", "UNKNOWN")
        for entry in migration_entries if isinstance(entry, dict)
    ))
    last_event = None
    event_type_counts = {}
    if events:
        event_type_counts = dict(Counter(event.get("event_type", "UNKNOWN") for event in events))
        last = events[-1]
        last_event = {
            "event_type": last.get("event_type"),
            "created_at": last.get("created_at"),
            "actor": last.get("actor"),
        }
    resource_status_counts = dict(Counter(
        lease.get("status", "UNKNOWN") for lease in resources.values()
    ))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "epoch": {
            "status": epoch_status,
            "epoch_id": epoch_id,
            "revision": revision,
            "event_count": len(events),
            "event_type_counts": event_type_counts,
            "last_event": last_event,
        },
        "tasks": {
            "total": len(tasks),
            "status_counts": projection["status_counts"],
            "items": task_rows,
        },
        "resources": {
            "total": len(resources),
            "status_counts": resource_status_counts,
            "items": resource_rows,
        },
        "migration": {
            "candidate_count": len(migration_entries),
            "migration_status_counts": migration_status_counts,
            "promotion_status_counts": promotion_status_counts,
            "imported_count": sum(1 for entry in migration_entries
                                  if isinstance(entry, dict)
                                  and entry.get("migration_status") == "IMPORTED"),
            "archive_commit": migration_manifest.get("source_archive", {}).get("commit"),
            "archive_tree_sha": migration_manifest.get("source_archive", {}).get("tree_sha"),
        },
        "archive": {
            "file_count": inventory.get("file_count"),
            "total_bytes": inventory.get("total_bytes"),
            "tree_sha": inventory.get("tree_sha"),
        },
        "safety": {
            "uu_conf_automation_protected": True,
            "manual_user_edits_allowed": True,
            "v1_workflows_stopped": False,
            "production_cutover": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--output", default=str(OUTPUT_DEFAULT))
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not args.repository or not token:
        raise SystemExit("dashboard snapshot requires repository and read-only GITHUB_TOKEN")
    from runtime import GitHubContentsBackend
    backend = GitHubContentsBackend(args.repository, args.branch, token)
    state, _ = backend.read()
    migration = json.loads((ROOT / "storage/v2/migration/v1-source-manifest.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "docs/v2/legacy-v1-inventory.json").read_text(encoding="utf-8"))
    snapshot = build_snapshot(state, migration, inventory)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "read_only": True,
        "epoch_status": snapshot["epoch"]["status"],
        "revision": snapshot["epoch"]["revision"],
        "task_count": snapshot["tasks"]["total"],
        "migration_candidate_count": snapshot["migration"]["candidate_count"],
        "output": str(output),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
