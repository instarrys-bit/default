# Four-System Architecture (Canonical Target)

Status: canonical target contract. This document supersedes the parallel V1/V2 design descriptions where they conflict. It does not claim that cutover is complete; see [FOUR_SYSTEM_CUTOVER.md](FOUR_SYSTEM_CUTOVER.md).

## The four systems

### 1. Watchdog

The sole top-level scheduler and supervisor. It dispatches production work, monitors deadlines and heartbeats, detects stalled or failed operations, requests recovery through Storage Management, and verifies end-to-end completion. It must not directly mutate production outputs or storage internals.

### 2. Dashboard

A read-only presentation and operator entry point. It displays authoritative state, task and lease status, production progress, release evidence, audits, and exceptions. It must not own queues, duplicate state, or write production/storage records.

### 3. Production

The only ruleset production pipeline. Its stages are:

`discover -> collect -> normalize -> filter -> deterministic_review -> deduplicate -> conflict_check -> build -> publish -> verify`

It handles collection, filtering, review, DIRECT/PROXY/REJECT classification, ruleset construction, publication requests, and post-publication validation. REJECT decisions must follow deterministic evidence and any configured human-approval gate. There is no AI review subsystem.

Production's canonical output authority is limited to `rulesets/**` and the exact release metadata explicitly allowlisted by Storage Management. It cannot write queue internals, arbitrary repository paths, user modules, scripts, or configuration.

### 4. Storage Management

The sole owner of durable state and file lifecycle: task/state persistence, event history, leases, source snapshots, candidate and review artifacts, release manifests, lifecycle metadata, audit evidence, recovery records, immutable snapshots, and SHA/version baselines.

It manages the latest `modules/uu.conf` baseline SHA and change tracking in real time, but **never edits `modules/uu.conf`**. It provides validated interfaces to the other three systems and preserves recoverable history.

## Ownership and data flow

- Watchdog requests dispatch/recovery and observes verified outcomes.
- Production emits versioned, provenance-bearing artifacts and ruleset release intents.
- Storage Management validates schema, provenance, idempotency, expected revision/SHA, and write scope before persisting or publishing.
- Dashboard reads projections and evidence from Storage Management only.
- No system bypasses another system's ownership boundary.

## Hard exclusions

- Exactly four systems; no fifth system or parallel control plane.
- No GitHub Issues dependency: Issues are forbidden as queue, persistence, pointer, lease, checkpoint, state machine, or communication transport. GitHub PRs may be used for code review only.
- No external or internal Lusse dependency.
- No AI review flow.
- No retired generic writer guard or `fenced_file_writer.py`.
- No automated write access to `modules/uu.conf`, `modules/**`, or mapped scripts.

## Preserved user assets

`modules/uu.conf` remains the unique user configuration file and is byte-for-byte protected. All module files and associated scripts under `modules/**` are explicitly preserved; this architecture cleanup does not remove or rewrite them.

## State migration and retirement policy

A legacy queue, workflow, adapter, registry, or subsystem may be deleted only after all of the following are evidenced:

1. Its active callers and workflow triggers are mapped.
2. Every still-relevant task, lease, checkpoint, artifact, and audit record is migrated or explicitly archived with source SHA and provenance.
3. The replacement interface is deployed and verified.
4. No runtime import, workflow, permission, registry, or test depends on the retired component.
5. Full relevant test suites and end-to-end production validation pass.
6. Rollback to the last verified ruleset release is proven without touching user configuration.

Historical GitHub Issue references may remain in inert archives solely for provenance; no running code may query or mutate Issues.
