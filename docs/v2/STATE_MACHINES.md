# V2 State Machines and Recovery Semantics

## Task lifecycle

Allowed transitions:

- `QUEUED -> CLAIMED`
- `CLAIMED -> RUNNING`
- `RUNNING -> SUCCEEDED`
- `RUNNING -> FAILED`
- `CLAIMED -> QUEUED` only after verified lease expiry/recovery and when attempts remain
- `RUNNING -> QUEUED` only after verified worker loss/expiry and when attempts remain
- `FAILED -> QUEUED` only under an explicit retry policy and when attempts remain
- `FAILED -> DEAD_LETTER` when retry budget is exhausted
- `CLAIMED/RUNNING -> DEAD_LETTER` only through a recorded recovery decision when retry budget is exhausted

Terminal states: `SUCCEEDED`, `DEAD_LETTER`, `CANCELLED`.

No transition is performed by editing a projection. Every transition appends an event with expected revision, actor, reason, evidence and idempotency key.

## Task lease lifecycle

Task lease states: `NONE`, `ACTIVE`, `EXPIRED`, `RELEASED`.

A task lease may be renewed only while its current lease is live, using the same lease ID, owner and opaque token; renewal must strictly extend expiry and must not shorten below any active resource lease. Expiry is a separate event and is accepted only at or after the recorded deadline. A task may be requeued only after the task lease is expired/released and every resource lease held by that task is independently expired/released. Expiry does not by itself prove the task's result is absent; inspect result evidence first.

## Resource lease lifecycle

Resource lease states: `NONE`, `ACTIVE`, `EXPIRED`, `RELEASED`.

Resource leases are keyed independently from task leases. Renewal is allowed only before expiry, with the same lease ID and fencing token, and cannot extend beyond the owning task lease. Expiry is an explicit event; reacquisition after expiry increments the fencing token. A recovery action must:
1. read the current resource lease and fencing token;
2. verify expiry or authoritative worker termination;
3. compare-and-swap the exact lease ID/token;
4. append the release event;
5. read back and verify the resource is no longer held by that lease.

A stale worker cannot renew, mutate or release a resource after a newer fencing token exists.

## Release lifecycle

`STAGED -> PREPARED -> COMMITTED -> VERIFIED`

Failure states: `REJECTED`, `ABORTED`, `VERIFICATION_FAILED`.

- Staged artifacts are immutable and content-addressed.
- Prepare checks exact output allowlist, base SHAs, schema, provenance, duplicate/conflict gates and capacity.
- Commit is idempotent and records before/after SHAs.
- Verification fetches the published outputs independently and compares their content hashes and expected rule counts.
- A failed or partial release is not marked verified; the previous verified release remains the rollback target.

## Migration lifecycle

`DISCOVERED -> HASH_VERIFIED -> SCHEMA_VALIDATED -> LINEAGE_REVIEWED -> ACCEPTED`

Alternative outcomes: `QUARANTINED`, `REJECTED`, `DUPLICATE_LINKED`.

Migration never imports V1 task statuses or active leases into the V2 queue. V1 records remain addressable by archive branch, original path and blob SHA.
