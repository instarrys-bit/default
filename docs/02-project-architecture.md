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

## Automation program capability registry

`automation/program_registry.json` is the repository-wide catalog for every Python component under `scripts/` and every GitHub Actions workflow under `.github/workflows/`.

Each entry declares its responsibility, capabilities, invocation model, inputs, outputs, dependencies, permission boundary, and health-check method. Workflow script calls and workflow dispatch targets are checked against the declared dependency graph.

A new Python component or workflow must be registered in the same change. CI fails closed if a program file is missing from the registry, a stale path remains, or a workflow invokes/dispatches a program without declaring that dependency.

Registration is a prerequisite for future cross-program orchestration, not an automatic permission grant. Independent entry points remain available. The workflow's job-level permissions remain authoritative, and registration alone never authorizes publication, rule activation, or edits to `shadowrocket/ss.conf`.
