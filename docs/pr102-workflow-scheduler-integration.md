# PR102 — Workflow dispatch scheduler integration

## Scheduling

The one-shot scheduler now supports two reviewed adapter types:
- `python_cli`: exact registered Python entrypoint, no shell, temporary JSON input, isolated child environment.
- `github_actions_workflow`: exact registered workflow path, live active workflow identity, explicit caller allowlist, allowlisted ref, and exact declared workflow inputs.

Workflow dispatch API timeouts are bounded below the registered task lease. The scheduler dispatches at most the configured bounded task count per Watchdog invocation.

## Durable dispatch intent and duplicate prevention

Before making the non-idempotent GitHub workflow_dispatch POST, the scheduler writes a SHA-CAS-protected `dispatch_intent` to the claimed task. The intent records workflow ID/path, ref, requested head SHA, task ID, attempt number, unique per-attempt correlation ID/title, and preparation time.

The workflow input `automation_task_id` is injected by the adapter as `<task_id>-a<attempt>`; callers cannot override it. The workflow run-name includes this marker.

If the dispatch response is accepted, the task enters `VERIFYING`. If the HTTP response is ambiguous (timeout/network/5xx), the task also enters `VERIFYING` with an unknown dispatch state; the verifier searches for the correlated run instead of sending another dispatch.

If the runner crashes after the intent is persisted, lease recovery retains the intent. A queued task with an existing intent is never eligible for redispatch. The verifier reconciles it by correlation. If no run is visible, the task remains blocked for manual reconciliation; it is not blindly dispatched again. A dead-letter task with an unresolved intent can re-enter verification only through this evidence-backed reconciliation path.

A confirmed 4xx rejection clears the intent before the normal bounded task failure/retry transition.

## Independent workflow completion verification

The result verifier performs GitHub API reads before its CAS mutator, keeping the mutator pure and safe to replay. It requires a unique run matching:
- exact workflow ID;
- `workflow_dispatch` event;
- allowlisted branch;
- requested head SHA;
- exact per-attempt run-name correlation title.

It then fetches the run details independently and checks the same identity fields again. Queued/in-progress runs remain pending. A task becomes `SUCCEEDED` only when GitHub reports `status=completed` and `conclusion=success`. Other completed conclusions are failures and follow the bounded retry/dead-letter policy. Multiple matching runs or identity drift fail closed.

## Activation boundary

- All 51 execution adapters remain disabled; workflow adapters have empty caller allowlists.
- The Watchdog scheduler can only dispatch a workflow after its adapter and target orchestration are explicitly reviewed and enabled.
- CI uses fake GitHub clients. It does not dispatch real workflows.
- No workflow adapter is automatically enabled by this PR.
- No rulesets, DNS, routing policy, or `modules/uu.conf` are modified.
