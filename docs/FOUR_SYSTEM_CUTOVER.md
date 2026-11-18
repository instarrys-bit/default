# Four-System Cutover Audit

This is an execution gate, not a claim of completion. The repository currently contains overlapping legacy and V2 implementations. A safe one-pass deletion is not possible until active call graphs and state migration are reconciled.

## Protected paths

- `modules/uu.conf` — never modify, move, regenerate, or delete.
- `modules/**` — preserve every module and associated script. No cleanup changes are authorized here.
- `rulesets/**` — preserve current published outputs; Production may write only the approved release allowlist.

Baseline checked on 2026-11-18:
- `modules/uu.conf` blob SHA: `1de9fc80e7fae47974b114b4e4780499991803a5`
- `modules/AdBlock.sgmodule` blob SHA: `abc839751adeb19f87674db154b5650371307143`
- `modules/adblock/scripts/Clean_Pro.js` blob SHA: `9f229fdcc62461e8adab1e9301b1c617cdcc659b`

## Current blockers found during audit

1. **Issue-era queue migration is incomplete.** Legacy workflow names and registries remain, while the active Watchdog still imports the remote task scheduler/queue runtime. Removing those files now would break dispatch and recovery.
2. **Queue persistence has multiple competing representations.** The repository contains task queue JSON, queue pointers/bundles, migration/recovery workflows, and V2 storage code. A canonical durable store and migration of live task/lease state must be selected before deleting any representation.
3. **Watchdog and recovery overlap.** Several scheduled workflows and adapters remain active. Their trigger graph and ownership must be collapsed to one Watchdog entry point before retirement.
4. **Production is not yet isolated from orchestration.** Existing scheduler/adapter modules still combine queue operations, GitHub workflow dispatch, and production task execution.
5. **Dashboard has multiple generations.** The legacy dashboard and V2 dashboard must be reconciled to one read-only view backed by Storage Management projections.
6. **Existing open PRs are not a safe substitute for this cutover.** PR #603 retains Issue-comment persistence and is incompatible with the no-Issues requirement. PR #632 is a separate config-baseline change and must be revalidated against the current base before reuse.

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
