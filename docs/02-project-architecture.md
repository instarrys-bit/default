# Project Architecture

## Mission and scope

This repository builds, validates, publishes, and maintains effective Shadowrocket domain rule sets for consumption by the user's Shadowrocket configuration.

The system's deliverable is the published rule-set data:

- `DIRECT`
- `PROXY`
- `REJECT`

The automation does not maintain the Shadowrocket module, its supporting scripts, MITM behavior, client deployment, or the user's configuration file. It may read `modules/uu.conf` to register an owner-approved baseline and audit rule conflicts or references. It must never modify that file.

## Architecture

| Layer | Main components | Responsibility |
|---|---|---|
| 1. Supervision | `.github/workflows/automation-watchdog.yml` | Monitor production audits, task queue, stale runs, manifest integrity, and bounded recovery |
| 2. Task control | `automation/task_queue.json`, `scripts/task_scheduler.py`, remote queue runtime | Persist, claim, dispatch, recover, and verify work |
| 3. Program contracts | `automation/program_registry.json`, `automation/execution_adapters.json` | Register every program, declare capabilities and dependencies, enforce deny-by-default execution |
| 4. Rule production | `.github/workflows/auto_sync.yml`, `scripts/` | Discover sources, collect candidates, review evidence, resolve conflicts, maintain lifecycle, and build lists |
| 5. Publication and evidence | `rulesets/`, `reports/`, independent verifier | Publish allowlisted outputs, reconcile manifest, preserve provenance and audit evidence |

These are logical layers, not a requirement that every component be a separate GitHub Actions workflow.

## Watchdog control plane

The Watchdog is the top-level event-driven supervisor. It runs on hourly and daily schedules, manual dispatch, relevant main-branch pushes, and completion of selected workflows.

Its jobs cover:

- `health-check`: audit freshness, infrastructure recovery, and source-discovery health.
- `stale-run-watch`: cancel superseded or stalled main-branch production audits and reconcile current main.
- `manifest-integrity`: verify and, within its narrow allowlist, reconcile manifest metadata.
- `task-queue-supervision`: recover expired leases, verify pending results, and execute one bounded queue task per run.

The Watchdog is not a permanently running daemon. GitHub Actions events and schedules wake it. Queue mutations use GitHub Contents API compare-and-swap (CAS); production publication has a separate main-writer concurrency boundary.

## Durable task orchestration

`automation/task_queue.json` is the program-execution queue. It is not the domain overflow queue.

A task moves through:

`QUEUED -> CLAIMED -> VERIFYING -> SUCCEEDED`

Failures move through a bounded retry path or to `DEAD_LETTER`. Workflow dispatch intent, task correlation, lease information, run evidence, and independent verification are persisted. CAS prevents concurrent queue updates from silently overwriting one another.

`rulesets/pending_queue.json` is separate. It holds qualified domain rules that cannot yet enter the published lists because of the 30,000-rule capacity limit.

## Program registry and adapters

`automation/program_registry.json` is the inventory of Python components and GitHub Actions workflows. `automation/execution_adapters.json` defines the execution contract for those registered programs.

Registration does not grant execution permission. A target must be explicitly enabled, have a reviewed interface, declare allowed callers, and satisfy its input/output and timeout contracts. Workflow dispatch additionally requires the caller job's GitHub permissions.

At the current architecture revision, the inventory contains 53 program records (47 Python components and 6 workflows) and 53 matching adapter records. The production audit workflow and the self-healing test workflow are the only enabled workflow adapters. The remaining Python components are still invoked as fixed pipeline steps where declared; they are not all independent queue workers.

## Rule production data flow

1. Discover candidate source repositories and rule files.
2. Assess parser support, publisher status, policy evidence, stability, and source lineage.
3. Admit only sources meeting deterministic policy gates.
4. Collect and normalize domain candidates.
5. Review independent evidence, confidence, policy conflicts, protected domains, and user-config conflicts.
6. Build the three policy lists within the capacity limit.
7. Apply conservative lifecycle checks and preserve deletion/restoration evidence.
8. Validate rule formats, manifest counts, source provenance, and references.
9. Publish only validated, allowlisted rule-set artifacts through the separately permissioned publisher.

No AI or LLM review is part of this pipeline.

## State and permission boundaries

| Resource | Automation boundary |
|---|---|
| Source registry, candidates, snapshots, review cursor | Maintained by deterministic source and review workflows |
| DIRECT / PROXY lists | Maintained by approved deterministic policy |
| New REJECT rules | Candidate evidence may be prepared; human approval remains mandatory |
| Manifest, lifecycle state, provenance, reports | Maintained and independently validated |
| Automation task queue | Maintained through CAS-backed queue operations |
| `modules/uu.conf` | Read-only baseline and conflict/reference audit; never edited |
| Shadowrocket modules, supporting scripts, MITM, deployment | Outside this repository automation system's maintenance scope |

The audit job uses read-only repository content permission. The publisher receives content write permission only for the allowlisted rule-set artifacts and related approved metadata. The publisher checks its audited base before writing and independently verifies the remote result.
