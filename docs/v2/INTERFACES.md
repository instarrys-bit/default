# V2 Subsystem Interface Contracts

These contracts define ownership and message boundaries before runtime code is ported.

## 1. Storage Management API (authoritative data owner)

All state-changing requests are authenticated, schema-validated, idempotent and append an immutable event. A successful response includes the event ID, resulting revision, and a read-back verification reference.

| Operation | Caller | Required input | Result |
|---|---|---|---|
| `queue.bootstrap` | operator/bootstrap job | approved empty seed SHA, epoch ID | initialized epoch + revision |
| `queue.append_event` | Watchdog / Storage internal | event type, task ID, expected revision, idempotency key | event ID + new revision |
| `queue.read_projection` | all authorized readers | projection name, optional cursor | projection + revision |
| `task.claim` | Watchdog | task ID, worker ID, expected revision, TTL, idempotency key | task lease + fencing token |
| `task.complete` | worker via Storage | task ID, lease token, result artifact SHA | terminal event |
| `resource.acquire` | worker via Storage | resource key, task ID, TTL, idempotency key | resource lease + fencing token |
| `resource.renew` | active worker via Storage | resource key, lease ID, fencing token, new expiry | renewed lease event |
| `resource.expire` | Watchdog recovery via Storage | resource key, lease ID, fencing token, observed expiry | expired lease event |
| `resource.release` | worker / recovery via Storage | resource key, lease ID, fencing token, reason | release event |
| `task.lease.renew` | active worker via Storage | task ID, lease ID, owner, opaque token, new expiry | renewed task lease event |
| `task.lease.expire` | Watchdog recovery via Storage | task ID, lease ID, owner, opaque token, observed expiry | expired task lease event |
| `artifact.stage` | Production | artifact type, content SHA, provenance, schema version | immutable staged artifact ID |
| `release.prepare` | Production | staged artifact IDs, exact output manifest, expected base SHAs | release candidate ID |
| `release.commit` | authorized publisher in Storage | candidate ID, approval/gate evidence, idempotency key | committed release ID + output SHAs |
| `release.verify` | independent verifier | release ID, remote target | verification report |
| `audit.query` | Dashboard / operator | scope, time/cursor | evidence records |

Storage Management is the only component allowed to mutate durable queue, event, lease, artifact, projection and release state. Callers cannot write these stores directly.

## 2. Watchdog contract

Watchdog is the only top-level scheduler. It:
- discovers due work and submits dispatch intents;
- asks Storage Management to claim tasks and acquire resource leases;
- starts Production workers using immutable task payload references;
- observes heartbeats and deadlines;
- requests recovery through Storage Management, never by editing queue files;
- accepts completion only when independent result verification succeeds.

Watchdog must not write ruleset files, source datasets, queue JSON, lease registries or `modules/uu.conf` directly. The `modules/uu.conf` restriction is scoped to automated workflows and automation identities only; it does not restrict manual edits by the user.

## 3. Production contract

Production stages are independent, resumable workers:

`discover -> collect -> normalize -> deterministic_assess -> deduplicate -> conflict_check -> build_candidate -> prepare_release`

Each stage consumes immutable input artifact IDs and emits immutable output artifacts with:
- schema version;
- source/provenance references;
- content SHA-256;
- task ID and idempotency key;
- producer version;
- created-at timestamp;
- validation result.

Production cannot commit durable queue transitions or directly publish to canonical repository outputs. It submits a release candidate to Storage Management.

No AI review flow is part of V2. REJECT eligibility and any required manual approval are deterministic, explicit gates.

## 4. Dashboard contract

Dashboard reads only Storage Management projections and verified release/audit artifacts. It must display:
- projection revision and generated-at timestamp;
- task status separately from task-lease status;
- resource lease owner, expiry and fencing token;
- latest production stage and artifact references;
- release ID, output SHAs and independent verification status;
- unknown/unavailable values explicitly.

Dashboard has no write endpoint for queue, production, release or configuration state.

## 5. Cross-cutting semantics

- **Idempotency:** every mutating request carries a stable idempotency key scoped to the operation.
- **Concurrency:** state changes use expected revision / SHA-CAS; stale writes are rejected, never silently retried with a refreshed base.
- **Fencing:** every acquired resource lease has a monotonically increasing fencing token. A stale token cannot write or release a newer lease.
- **Expiry:** task lease expiry and resource lease expiry are evaluated independently and recorded as explicit events. Expired leases cannot be renewed; task requeue is blocked until all resource leases for the task are released or expired.
- **Events:** state changes are append-only. Projections are rebuildable and never authoritative.
- **Verification:** write success is not publication success; independent read-back verification is mandatory.
- **Unknown state:** missing or contradictory evidence is represented as unknown and held for reconciliation, not inferred as success.
- **Failure:** retries are bounded and idempotent; exhausted work enters DEAD_LETTER with retained evidence.
