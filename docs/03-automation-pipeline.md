# Automation Pipeline

## Operating model

The pipeline is deterministic and designed for unattended ruleset production. It does not depend on AI, LLM services, model APIs, or manual per-domain classification.

Its only business deliverable is the validated DIRECT, PROXY, and REJECT rule sets consumed by the user's Shadowrocket configuration. The automation does not maintain that configuration, modules, module scripts, MITM behavior, or client deployment. The configuration is read-only for baseline and conflict audits.

## Production entry points

- `.github/workflows/automation-watchdog.yml` owns production scheduling and queue supervision.
- Relevant main-branch changes, hourly/daily schedules, selected workflow completions, and manual Watchdog dispatch wake the supervisor.
- `.github/workflows/request-intake.yml` accepts up to 500 hostname-only observations, persists them as unclassified candidates, then dispatches the Watchdog. It does not dispatch the production audit directly.
- `.github/workflows/auto_sync.yml` is a queue-owned production worker. Its required `automation_task_id` must match a persisted Watchdog-created task and dispatch intent in `automation/task_queue.json`. A direct/manual run without a valid queue record is rejected.
- `.github/workflows/self-healing-agent.yml` diagnoses selected workflow failures and may create a narrowly scoped repair PR. The self-healing test workflow is a separately authorized validation target.

GitHub documents that workflow dispatch events are an exception to the normal rule that events created with `GITHUB_TOKEN` do not start new workflow runs. This permits request intake to wake the Watchdog without directly invoking the production worker.

## Watchdog and task execution

The Watchdog has four responsibilities:

1. Check audit freshness, source-discovery health, and recoverable infrastructure failures.
2. Detect stale or stalled production audits and avoid cancelling feature-branch work.
3. Verify manifest integrity and run narrowly scoped metadata reconciliation.
4. Recover expired queue leases, independently verify completed results, and dispatch one bounded task per queue-supervision run.

Watchdog workflow runs use unique concurrency groups so a later event cannot replace an earlier pending event in the same shared group. Queue state changes use GitHub Contents API CAS. The production publisher retains its own main-writer serialization boundary.

## Failure and recovery policy

Recovery distinguishes three cases:

| Failure class | Policy |
|---|---|
| Infrastructure timeout or startup failure | Bounded retry through a new durable task, with same-SHA history checks and cooldown |
| Deterministic failure on the same reviewed inputs | Do not retry automatically; preserve evidence for diagnosis and safe repair |
| Audit superseded by meaningful main-branch input changes | Do not retry the stale task; enqueue a new audit against current main, preserving its original task input |

The infrastructure recovery policy allows at most two retries within its policy window, with a 15-minute base cooldown and increasing cooldown for later attempts. Each queue task itself remains single-attempt. A successful workflow dispatch is not considered task success until the independent verifier confirms the correlated run identity and completed conclusion.

The publish-base guard permits only documentation-only advances and strictly verified durable queue-state commit chains. Changes to policy inputs, scripts, the protected configuration baseline, or other non-allowlisted state make the old audit stale. If comparison evidence is unavailable or ambiguous, the system fails closed and waits for a later reconciliation rather than publishing stale output.

## Rule production stages

1. **Source discovery:** search supported public repositories and candidate rule files without activating them.
2. **Source assessment:** verify parser support, publisher status, policy evidence, file size and read limits, stable observations, and content hashes.
3. **Source lineage:** identify shared upstreams and avoid treating forks or mirrors as independent evidence.
4. **Collection:** fetch admitted sources and normalize supported domain entries.
5. **Deterministic review:** compare evidence across independent publishers/source groups, apply confidence thresholds, and quarantine contradictions.
6. **Conflict handling:** remove or hold candidates that conflict with the owner-controlled configuration baseline or protected-domain policy.
7. **Build:** generate separate DIRECT, PROXY, and REJECT lists.
8. **Lifecycle:** run conservative deletion checks and preserve archives/restoration records.
9. **Validation and publication:** validate formats, counts, references, manifest, provenance, and protected baseline; publish only allowlisted artifacts from the separate writer job.

## Rule policy and capacity

The published output contains only DIRECT, PROXY, and REJECT.

- The published capacity limit is 30,000 rules.
- Qualified overflow rules are held in `rulesets/pending_queue.json`, separate from the automation task queue.
- Lifecycle review is triggered at each 5,000-rule milestone and monthly after capacity is reached.
- Automatic deletion requires conservative dual-resolver A/AAAA evidence and two observations separated by at least 30 days.
- Protected and critical domains are not automatically deleted; deletion evidence and restoration options are retained.
- New REJECT rules require human approval. Automation may collect and present evidence but may not grant that approval.

## Persistence and publication

Source snapshots, review cursors, task state, lifecycle state, provenance, and manifests are repository-backed durable state, not disposable runner cache.

The audit job is read-only with respect to repository contents. It packages only allowlisted outputs. The separate publisher checks the audited base, refuses unsafe rebase or mixed changes, publishes the permitted rule-set artifacts, and independently verifies the remote files and manifest.

A successful GitHub Actions run alone is not proof that every source is healthy. Review the generated reports, task queue evidence, and publication verification result.

## Configuration boundary

`shadowrocket/ss.conf` is an owner-controlled input to conflict and reference checks. The ruleset automation may read it, register an owner-approved baseline, and report conflicts. It must not edit it, change DNS, alter routing policy, or manage Shadowrocket modules and MITM behavior.
