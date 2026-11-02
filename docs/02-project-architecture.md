# Project Architecture

## Repository layout

| Path | Responsibility |
|---|---|
| `.github/workflows/` | Scheduled, manual, intake, validation, and watchdog workflows |
| `shadowrocket/ss.conf` | User-owned authoritative Shadowrocket configuration |
| `rulesets/` | Three published lists, manifest, queue, lifecycle state, and conflict archive |
| `sources/` | Source registry, candidate inventory, review ledger, policy, and protection metadata |
| `scripts/` | Collection, parsing, deterministic review, audits, building, and validation |
| `data/` | Candidate data and persistent source snapshots |
| `reports/` | Generated audit, lifecycle, source, conflict, and status reports |
| `modules/` | Optional modules and supporting scripts |

## Data flow

1. Fetch enabled sources from the registry.
2. Parse supported domain entries and normalize them.
3. Persist source snapshots for cross-run change detection.
4. Review candidates against current evidence and safety gates.
5. Check policy conflicts, protected domains, and the authoritative configuration.
6. Build DIRECT, PROXY, and REJECT lists within the global capacity limit.
7. Run static validation and generate reports.
8. Publish only validated, allowlisted artifacts through the separate writer job.

## State boundaries

Registries, ledgers, queues, archives, and snapshots are persistent project state, not disposable runner cache. Reports describe specific executions and do not override policy files or executable behavior.

The manifest records publication counts and lifecycle changes. The automation's output directory is limited to `direct.list`, `proxy.list`, and `reject.list`.