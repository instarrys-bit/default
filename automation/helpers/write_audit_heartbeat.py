#!/usr/bin/env python3
"""Write successful audit heartbeat."""
import json
import os
import sys
from datetime import datetime, timezone
sys.path.insert(0, "scripts")
from production_intent import load_manifest, compute_fingerprint, compute_output_fingerprint
from pathlib import Path
Path("reports/automation").mkdir(parents=True, exist_ok=True)
manifest = load_manifest(Path("automation/production_inputs.json"))
input_fingerprint = os.environ["PRODUCTION_INPUT_FINGERPRINT"]
post_run_input_fingerprint = compute_fingerprint(Path("."), manifest)
output_fingerprint = compute_output_fingerprint(Path("."))
record = {
    "schema_version": 3,
    "input_fingerprint": input_fingerprint,
    "post_run_input_fingerprint": post_run_input_fingerprint,
    "output_fingerprint": output_fingerprint,
    "input_manifest_schema_version": manifest["schema_version"],
    "status": "audit_passed",
    "workflow": "Shadowrocket Deterministic Domain Audit (User Config Baseline)",
    "run_id": os.environ["GITHUB_RUN_ID"],
    "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
    "event": os.environ["GITHUB_EVENT_NAME"],
    "source_commit": os.environ["GITHUB_SHA"],
    "production_decision": os.environ.get("PRODUCTION_DECISION", ""),
    "production_reason": os.environ.get("PRODUCTION_REASON", ""),
    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    "checks": {
        "deterministic_tests": "passed",
        "user_config_baseline": "passed",
        "config_conflict_sync": "passed",
        "lifecycle_audit": "passed",
        "three_policy_rule_sets": "passed",
        "config_validation": "passed",
        "source_and_rule_audits": "passed"
    },
    "protected_config": {
        "path": "modules/uu.conf",
        "modified_by_automation": False
    }
}
with open("reports/automation/heartbeat.json", "w", encoding="utf-8") as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
