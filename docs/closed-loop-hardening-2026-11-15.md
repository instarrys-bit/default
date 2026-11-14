# Durable Queue Snapshot Artifact (closed-loop hardening)

## Why
Issue #421 root cause: the only full queue state lived in Issue comments. When Issue #315 was deleted, recovery became impossible. Watchdog already exported the snapshot to $RUNNER_TEMP but never persisted it as an Actions artifact.

## Fix
After every successful "Export durable queue snapshot" step, upload the snapshot as an artifact (see queue-snapshot-upload-blocks.md for the exact YAML).

## Current closed-loop state (2026-11-15)
- Source Candidate Registry: schema-v2 sharded (49 115 records, 2 shards, ~39.9 MB). Last discovery run 42905899022.
- Baseline: modules/uu.conf registered at blob 08e7add5... (synced 2026-11-14).
- Queue: Issue #423 is the live store; historical revision 610 correctly treated as unrecoverable.
- Assessment: 9 018 assessments present; next batches continue from recorded cursor under 20-file budget.

## Safety
- No change to queue schema, CAS, leases, or production write boundaries.
- modules/uu.conf remains read-only.
- Existing pinned actions are reused.
