# Automation Pipeline

## Operating model

The project is designed for deterministic unattended operation. The review and build pipeline must not depend on AI, LLM services, model APIs, API keys, or manual per-domain review.

The principal publisher workflow is `.github/workflows/auto_sync.yml`. It runs weekly on Monday at 04:00 Beijing time, on relevant pushes, or by manual dispatch. The top-level `automation-watchdog.yml` owns hourly stale-run monitoring, bounded audit recovery, and daily manifest-integrity checks. The `self-healing-agent.yml` is event-driven and handles failure diagnosis, allowlisted repair proposals, and incident lifecycle processing. The Watchdog only cancels stale or superseded main-branch audits; it does not cancel feature-branch runs.

Source discovery searches bilingual and open-source project keywords with up to 10 GitHub Search pages per query, reads up to 1,000 repository READMEs, and scans up to 500 repository Git Trees (up to 3,000 entries per tree) for `.list`, `.txt`, and `.conf` candidates. Discovery does not assign policy or activate sources. The assessor is bounded to 5,000 URLs, 5 MB per file, and 250 MB total read data; downstream overlap audit allows 30 MB per file and 500 MB total.

## Pipeline stages

1. **Collection:** fetch enabled registry sources.
2. **Parsing:** use only explicitly supported parsers.
3. **Normalization:** canonicalize supported domain entries and remove duplicates.
4. **Evidence review:** compare current evidence across independent publishers and source groups.
5. **Safety gates:** hold policy conflicts, protected domains, configuration conflicts, and unsupported scopes.
6. **Build:** generate the three policy lists and apply queue/capacity rules.
7. **Validation:** verify formats, policy separation, references, and protected-config integrity.
8. **Reporting:** update source, lifecycle, conflict, and project-status reports.
9. **Publication:** a separately permissioned job publishes approved artifacts.

## Permission separation

The intended workflow design separates audit, publication, and notification:

- Audit jobs use read-only contents permission and do not retain checkout credentials.
- Only the dedicated publisher receives contents write permission.
- The publisher consumes short-lived allowlisted artifacts and rechecks the expected base commit.
- The publisher must not execute repository Python scripts with write credentials.
- Failure notification receives issue-writing permission only where needed.

The writer uses fail-closed rebase behavior. It must never resolve output conflicts by blindly preferring the automation branch.

## Retry policy

Transient network failures, including HTTP 408, 425, 429, 5xx responses, and network timeouts, receive at most three bounded attempts with backoff. Permanent 4xx responses, malformed content, and safety-gate failures are not retried as transient failures.

A later successful full audit and publication may close the corresponding fault issue.

## Persistence

Source snapshots and project ledgers must survive runner replacement. A successful workflow run does not prove every source is healthy or every device behavior is correct; consult reports and perform target-device validation.
## Observed-domain intake

The manual GitHub Actions workflow `GitHub-only observed-domain intake` accepts up to 500 plain hostnames per submission. It validates and merges them into `sources/request_domain_observations.json`, then triggers deterministic review. It must not accept full URLs, query strings, request headers, request bodies, or client identifiers.

This is not a continuously listening service. Device logs must first be reduced to hostnames and then imported manually; no automatic real-time phone push is provided.

## Watchdog behavior

The top-level Watchdog has two distinct audit-health checks:

- An hourly stale-run monitor cancels a main-branch audit only when it is superseded by non-documentation changes or has run for more than six hours. It then checks that no main-branch audit remains active before considering replacement.
- A daily audit-freshness check uses an eight-day threshold for the weekly audit schedule. It dispatches a bounded replacement only when the latest successful audit is stale or its audited code inputs have been superseded.

These are recovery triggers, not guarantees that GitHub Actions or external dependencies will always succeed.


## Program registration and collaboration

Every Python component in `scripts/` and every workflow in `.github/workflows/` is recorded in `automation/program_registry.json`. New program files must add a registry entry in the same change; workflow-to-script calls and workflow dispatches must also be declared. CI validates the inventory and dependency edges and rejects unregistered additions.

Registration does not force programs into a central runtime. Each program keeps its own scheduled, event-driven, manual, or imported entry point. The registry is the contract for future coordination: Watchdog and any later scheduler may only consider registered capabilities and declared dependencies. Automatic invocation still requires an explicit dispatch policy and the target workflow's existing permissions.

The registry is descriptive and fail-closed; it does not grant GitHub permissions, activate sources, approve domain rules, publish artifacts, or permit automation to modify `shadowrocket/ss.conf`.


## Cross-program orchestration contract

The general task queue at automation/task_queue.json is deliberately separate from rulesets/pending_queue.json, which remains the domain-rule candidate queue.

Every task identifies its requester, target, requested capability, idempotency key, trace ID, priority, UTC schedule fields, retry budget, input, lease, result, and error. Validation rejects unknown programs, undeclared capabilities, disabled targets, unauthorized callers, duplicate idempotency keys, invalid timestamps, malformed leases, and retry budgets above the target's registered policy.

All programs currently default to orchestration disabled with an empty caller allowlist. This is an explicit deny-by-default posture. A registry entry alone does not authorize invocation.

The current implementation is a protocol and data-integrity gate, not a live scheduler. No existing workflow is dispatched from this queue yet. Lease acquisition, concurrency control, execution, timeout enforcement, retry transitions, dead-letter handling, and independent result verification remain later implementation steps.


## Local task-queue runtime primitives

The registered runtime module provides idempotent enqueue, priority-based claim, per-task lease tokens, bounded retry with backoff, and expired-lease recovery. Mutations use an advisory file lock plus fsync-and-rename atomic replacement. This serializes cooperating processes that share the same filesystem.

This is not yet a distributed queue or a cross-runner lock. Current GitHub Actions validation invokes only a CLI smoke check and unit tests; it does not enable a production worker, dispatch registered programs, or persist queue mutations back to the repository. A GitHub-backed single-writer/conditional-update adapter and an execution dispatcher are still required before production activation.

## Unified execution adapter standard

`automation/execution_adapters.json` is the one-to-one execution contract for every registered program. CI checks that its 46 adapter entries exactly match the 40 Python components and six GitHub Actions workflows in `automation/program_registry.json`.

- **Python components:** invocation is limited to the exact registered file path through `python3`, with a literal argument array and no shell. A Python target remains non-executable until its CLI input schema, output schema, timeout, and side effects have been reviewed and recorded. All current Python interfaces are marked `unreviewed`.
- **GitHub Actions workflows:** the contract records whether `workflow_dispatch` exists and mirrors its declared input names, types, and required flags. Four workflows are dispatchable; the event-only self-healing agent and push/PR config validator are not workflow-dispatch targets.
- **Authorization:** every adapter is disabled, every caller allowlist is empty, and retry budgets are zero. Enabling a target requires matching registry orchestration policy, reviewed interface contracts, explicit callers, bounded retries, and a ref allowlist. The adapter registry does not grant token permissions; a caller job must separately declare least-privilege permissions, including `actions: write` for workflow dispatch.
- **Completion:** a zero process exit or a successful GitHub Actions run is not sufficient by itself. The dispatcher must retain the workflow run ID and result metadata, then pass the result through an independent verifier before a task may become `SUCCEEDED`.
- **Current implementation boundary:** this PR establishes and validates the adapter contract only. It does not add a dispatcher, GitHub-backed queue persistence, worker activation, or automatic invocation. The task queue runtime remains local and all adapters remain disabled.

The adapter contract is distinct from `rulesets/pending_queue.json` and cannot authorize changes to `shadowrocket/ss.conf`.

