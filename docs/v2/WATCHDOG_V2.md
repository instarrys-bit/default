# V2 Watchdog Supervisor

## Responsibility

The V2 Watchdog is the top-level scheduler and recovery supervisor. It reads the event-sourced Storage Management state, evaluates task/resource lease deadlines, and prepares deterministic recovery action references.

## Current implementation boundary

The first V2 supervisor is intentionally read-only:
- It detects expired resource leases and plans resource-expiry events first.
- It then plans task-lease expiry events.
- It plans requeue only after all resource leases for the task are released or expired.
- It plans dead-letter instead of requeue when the retry budget is exhausted.
- It emits expected revisions and deterministic idempotency keys.
- It never emits opaque task lease tokens; Storage Management must rehydrate them from the current state after CAS validation.
- It does not dispatch workers because the V2 task routing schema and Storage Manager apply/dispatch interface are not yet enabled.

The scheduled workflow uses contents:read only and writes its report to the Actions job summary. It does not mutate state, renew/release leases, dispatch tasks, import V1 queue state, or publish rulesets.

## Next gate

Before enabling dispatch or recovery writes, complete:
1. Storage Manager apply endpoint that re-reads the current revision, rehydrates lease tokens, validates idempotency and CAS, then appends events.
2. V2 task schema with target program, input artifact IDs, priority, retry policy and allowed adapter.
3. Production worker adapter registry and bounded workflow dispatch.
4. Dual-run reconciliation against V1 without importing V1 task or lease state.

V1 Watchdog remains active until V2 dual-run, recovery and rollback evidence pass.
