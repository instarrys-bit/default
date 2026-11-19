# Shadowrocket repository

This repository has exactly four automation systems:

1. **Watchdog** — the only top-level scheduler; dispatches work, monitors execution, coordinates recovery, and verifies end-to-end results.
2. **Dashboard** — read-only operational view of authoritative state and evidence.
3. **Production** — source collection, filtering, deterministic review, DIRECT/PROXY/REJECT ruleset construction, publication request, and post-publication validation.
4. **Storage Management** — authoritative persistence, task/state records, artifacts, SHA/version baselines, audit evidence, snapshots, and recovery records.

## User-maintained subscription assets

These are repository deliverables, not additional automation systems:

- `modules/uu.conf` — the sole user configuration file. It is strictly read-only to automation.
- `modules/**` and their mapped scripts — user-maintained Shadowrocket modules and scripts. They are explicitly preserved and are outside this cleanup's deletion scope.
- `rulesets/direct.list`, `rulesets/proxy.list`, `rulesets/reject.list` — Production's published outputs.

## Non-negotiable boundaries

- Production's only canonical rule-output write scope is `rulesets/**`, further restricted by the release manifest.
- Production cannot modify `modules/uu.conf`, any module, or any mapped script.
- Storage Management owns the `uu.conf` baseline SHA/version/change tracking; it does not edit the file.
- Dashboard is read-only.
- Watchdog coordinates systems but does not bypass their ownership boundaries.
- GitHub Issues must not be used as a runtime queue, state store, lease store, pointer, checkpoint, or inter-system transport. Historical issue references may remain only in clearly marked inert archival records.
- No fifth subsystem, external Lusse dependency, or AI review subsystem is part of the target architecture.

## Subscription URLs

Configuration:
`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/uu.conf`

Module:
`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/AdBlock.sgmodule`

## Cutover status

The four-system architecture is the target contract. Legacy runtime components are not considered retired merely because documentation names the target. See [the cutover audit](docs/FOUR_SYSTEM_CUTOVER.md) for remaining implementation and validation gates. Do not remove a legacy component until its replacement is live, its persisted state is reconciled, and its dependent workflows/tests have passed.
