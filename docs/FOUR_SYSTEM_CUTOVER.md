# Four-System Cutover Audit

This is an execution record and retirement gate, not a claim of full cutover. The primary task queue is already stored in repository JSON through GitHub Contents API SHA-CAS. The V2 event-sourced store is not yet the live queue backend, and active incident workflows still contain GitHub Issues operations.

## Protected paths

- `modules/uu.conf` — never modify, move, regenerate, or delete.
- `modules/**` — preserve every module and associated script. No cleanup changes are authorized here.
- `rulesets/**` — preserve current published outputs; Production may write only the approved release allowlist.

Baseline checked on 2026-11-18:
- `modules/uu.conf` blob SHA: `1de9fc80e7fae47974b114b4e4780499991803a5`
- `modules/AdBlock.sgmodule` blob SHA: `abc839751adeb19f87674db154b5650371307143`
- `modules/adblock/scripts/Clean_Pro.js` blob SHA: `9f229fdcc62461e8adab1e9301b1c617cdcc659b`

## Retirements completed in this branch

- Deleted the completed Issue-to-repository queue migration workflow.
- Deleted the duplicate five-minute V2 Watchdog schedule and its registry/adapter declarations.
- Deleted the stale queue pointer containing Issue index/backend references.
- Removed the Issue-number compatibility switch from the repository-JSON queue store; it now uses Contents API SHA-CAS only.
- Removed Issue #317 request-observation fetching; Production now reads the checked-in observation seed only.
- Removed unused Issues permissions from Source Discovery, queue snapshot, Dashboard, and queue lease recovery workflows.
- Replaced the old Issue-comment queue-store test suite with tests for repository JSON Contents API behavior.

## Current blockers found during audit

1. **Incident Issues remain active.** `auto_sync.yml`, `automation-watchdog.yml`, and `self-healing-agent.yml` still create/update/close GitHub Issues for failure and recovery incidents. These must move to Storage Management before all Issues permissions and API calls can be removed.
2. **The V2 event-sourced store is not yet live.** `storage/v2/queue_seed.json` is an empty bootstrap template; no verified migration has promoted the live task queue and leases into `storage/v2/state.json`.
3. **Queue state must remain intact.** The active repository JSON queue is revision 877 with 160 tasks (39 SUCCEEDED, 89 CANCELLED, 29 DEAD_LETTER, 3 QUEUED) and 23 resource-lease records. The queue and historical snapshots are preserved; no tasks were reset or replayed.
3. **Watchdog and recovery overlap.** Several scheduled workflows and adapters remain active. Their trigger graph and ownership must be collapsed to one Watchdog entry point before retirement.
5. **Production is not yet isolated from orchestration.** Existing scheduler/adapter modules still combine queue operations, GitHub workflow dispatch, and production task execution.
6. **Dashboard has multiple generations.** The legacy dashboard and V2 dashboard must be reconciled to one read-only view backed by Storage Management projections.
7. **Existing open PRs are not a safe substitute for this cutover.** PR #603 retains Issue-comment persistence and is incompatible with the no-Issues requirement. PR #632 is a separate config-baseline change and must be revalidated against the current base before reuse.

## Required execution sequence

- [ ] Inventory every tracked path into Watchdog, Dashboard, Production, Storage Management, protected user assets, or inert archive/support.
- [ ] Define one Storage Management persistence backend and stable interfaces; remove all GitHub Issues API/runtime access.
- [ ] Migrate live queue/task/lease/checkpoint state with source SHA, revision, idempotency and recovery evidence. Do not reset or replay tasks.
- [ ] Convert every active workflow to the four-system ownership model; leave one Watchdog scheduler and one Dashboard deployment.
- [ ] Move production stages behind the Production interface; enforce write scope at the storage boundary and in tests.
- [ ] Move `uu.conf` baseline registration/SHA/change tracking into Storage Management, with read-only byte verification.
- [ ] Remove superseded adapters, duplicate registries, old queue mechanisms, and obsolete workflows only after zero active references are proven.
- [ ] Keep modules/scripts and published rulesets intact.
- [ ] Run unit, integration, workflow/YAML, permission, migration, concurrency, recovery, output-scope, subscription and post-publish verification.
- [ ] Open/refresh a PR with complete changed-file list and verify `uu.conf` and all `modules/**` blobs are unchanged.

## Non-negotiable acceptance checks

- Exactly four operational systems.
- No GitHub Issues API calls, issue permissions, issue pointers, or issue-backed state in runtime workflows.
- No Lusse dependency.
- Production writes only allowlisted `rulesets/**` release outputs.
- Dashboard has no write authority.
- Watchdog is the only top-level scheduler.
- Storage Management is the only durable-state owner.
- `modules/uu.conf` and every module/script remain byte-identical.
- No tasks are silently discarded, reset, or replayed.
- All migration and end-to-end verification evidence is attached to the cutover PR.
