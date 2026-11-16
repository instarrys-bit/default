# Storage Management — Watchdog Recovery Apply

Storage Management is the only component that applies Watchdog recovery plans.

## Apply contract

- Re-read the current V2 state and verify epoch ID plus base revision.
- Require actor storage_management and the exact storage/v2/state.json write allowlist.
- Reject any plan containing an opaque task lease token.
- Rehydrate task lease tokens from the current projection by task ID, lease ID and owner.
- Revalidate resource lease ID/fencing token, task lease identity/status and every expected revision.
- Append exactly one event per GitHub Contents CAS commit; verify each commit by independent read-back.
- Stop immediately on a CAS conflict. Previously committed events remain valid; Watchdog must re-read and re-plan.
- Never dispatch a worker or publish a ruleset as part of recovery apply.

The endpoint supports resource expiry, task expiry, task requeue and dead-letter events. Task requeue is applied only after the plan has expired/released the task lease and every resource lease is expired/released. The append-only event log retains the lease token inside the event payload for authorization evidence; API results and Watchdog plans never return that token.

## Activation

The apply functions are implemented and unit-tested but no workflow invokes them. They require an already initialized V2 epoch and a Storage Management credential. No epoch bootstrap, V1 task/lease import, automatic worker dispatch or production cutover is enabled.
