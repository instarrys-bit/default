# Automation Pipeline

## Operating model

The project is designed for deterministic unattended operation. The review and build pipeline must not depend on AI, LLM services, model APIs, API keys, or manual per-domain review.

The principal publisher workflow is `.github/workflows/auto_sync.yml`. It supports manual execution and scheduled execution. A separate watchdog checks the latest successful run and may redispatch an audit when the configured health conditions are met.

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