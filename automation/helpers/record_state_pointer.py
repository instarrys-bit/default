#!/usr/bin/env python3
"""Record durable automation state pointer."""
import json, os, sys
sys.path.insert(0, "scripts")
from pathlib import Path
from datetime import datetime, timezone
Path("reports/automation").mkdir(parents=True, exist_ok=True)
record = {
    "schema_version": 1,
    "last_state_run_id": os.environ["GITHUB_RUN_ID"],
    "source_commit": os.environ["GITHUB_SHA"],
    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    "artifact_name": "deterministic-audit-output",
    "artifact_retention_days": 90,
    "storage_mode": "github_actions_artifact",
    "missing_artifact_policy": "fail_closed"
}
with open("reports/automation/state_store.json", "w", encoding="utf-8") as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
