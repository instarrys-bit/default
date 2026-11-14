# Durable Queue Snapshot Artifact (closed-loop hardening)

## Why
Issue #421 root cause: the only full queue state lived in Issue comments. When Issue #315 was deleted, recovery became impossible. Watchdog already exported the snapshot to $RUNNER_TEMP but never persisted it as an Actions artifact.

## Fix (this branch)
After every successful "Export durable queue snapshot" step in automation-watchdog.yml, the snapshot is uploaded as:

- durable-queue-snapshot-<run_id>-health
- durable-queue-snapshot-<run_id>-supervision

retention-days: 30, if: always(), if-no-files-found: ignore.

This makes the canonical queue state recoverable independently of Issue comment history.

## Safety
- No change to queue schema, CAS, leases, or production write boundaries.
- modules/uu.conf remains read-only.
- Existing pinned actions are reused.

## Current state of the closed loop (2026-11-15)
- Source Candidate Registry: already schema-v2 sharded (49 115 records, 2 shards, ~39.9 MB total, last discovery run 42905899022).
- Baseline: modules/uu.conf registered at blob 08e7add5... (synced 2026-11-14).
- Queue: Issue #423 is the live store; historical revision 610 is unrecoverable and was correctly not reconstructed from stale revision 250.
- Assessment: 9 018 assessments present; next batches can continue from the recorded cursor under the existing 20-file budget.

## Remaining operator actions after this PR merges
1. Merge this PR.
2. Let the next Watchdog schedule (or a manual dispatch) run; confirm the new artifacts appear.
3. Continue Assessment batches via the existing queue handoff (no activation without eligibility).
4. Close tracking Issues #421, #447, #423 (and the self-healing noise issues) with the run evidence.
