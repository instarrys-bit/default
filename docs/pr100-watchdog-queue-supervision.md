# PR100 — Watchdog-owned queue supervision

## Top-level ownership

The existing `workflow_automation_watchdog` remains the top-level supervisor. This change extends that workflow rather than creating a second watchdog. Its new `task-queue-supervision` job runs after the health-check job on scheduled, manual, main-branch push, and supported workflow-completion events.

The job performs one bounded scheduler pass:
1. recover expired remote task leases;
2. independently verify tasks waiting in `VERIFYING`;
3. plan eligible tasks against registry authorization and reviewed adapter contracts;
4. execute at most one eligible Python CLI task;
5. persist the result through the GitHub Contents SHA-CAS store.

## Permission and execution boundary

- Only the queue-supervision job receives `actions: write` and `contents: write`; it does not receive `issues: write`. The rest of the Watchdog retains its existing job-scoped permissions.
- Checkout uses `persist-credentials: false`.
- The workflow removes `GITHUB_TOKEN` from its shell environment and pipes it to the scheduler over stdin; the scheduler stores it only in the queue client.
- The scheduler strips credential-like variables from its own environment while child processes run, gives children a small non-secret environment allowlist, and closes child stdin.
- The job is serialized with the `shadowrocket-task-queue` concurrency group.
- Scheduler execution is bounded to one task per Watchdog invocation and to Python CLI adapters with enabled, reviewed interfaces and explicit caller allowlists.
- Workflow-dispatch adapters remain unsupported by this scheduler version and are blocked.
- Expired leases are recovered; verification failures retry under the existing bounded policy.
- Any detected child-process change to `modules/uu.conf` fails the task and stops the scheduler.

## Current activation state

All 50 registered execution adapters remain disabled. Therefore the Watchdog can recover leases, verify any already-pending results with an approved contract, and report blocked queue items, but it cannot launch any registered program at this time. CI validates the workflow and tests the scheduler using temporary fixture programs; it does not run production queue execution.

No rule sets, DNS, routing policy, or `modules/uu.conf` are changed by this PR.
