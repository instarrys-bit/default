# PR101 — GitHub Actions workflow adapter contract

## Purpose

This change establishes the deterministic API and correlation contract needed before GitHub Actions workflows can be scheduled as queue tasks. It does not yet connect the adapter to the production scheduler.

## Dispatch authorization

A dispatch request is valid only when:
- the target adapter is explicitly enabled and marked `workflow_dispatch_reviewed`;
- the requesting program appears in the adapter caller allowlist;
- the workflow is marked dispatchable and the requested ref is allowlisted;
- the live GitHub workflow metadata matches the registered path and is active;
- the supplied task inputs match the declared workflow inputs, including required fields and primitive types.

The caller cannot supply `automation_task_id`; the adapter injects the queue task ID as a reserved correlation value.

## Run correlation

Each dispatchable workflow has an optional `automation_task_id` workflow_dispatch input and a run-name derived from it. Manual dispatches remain usable; when the input is blank, the run name is `Automation task manual`.

The adapter identifies a run only when workflow ID, workflow_dispatch event, branch, requested head SHA, and exact correlation title all match. Multiple matches are treated as ambiguous and fail closed.

## Independent completion evidence

A successful HTTP dispatch response is not task success. The independent run inspection requires the exact correlated run to exist, rechecks its identity through the run-details endpoint, and accepts success only when GitHub reports `status=completed` and `conclusion=success`. Queued and in-progress runs remain pending; all other conclusions are failures.

## Activation boundary

- The dispatcher module is registered but its own execution adapter remains disabled and unreviewed.
- All existing workflow adapters remain disabled with empty caller allowlists.
- The production scheduler still executes only its existing reviewed Python CLI adapter path; this PR does not dispatch workflows.
- No workflow is automatically invoked by CI. Tests use a fake GitHub API client.
- No rulesets, DNS, routing policy, or `modules/uu.conf` are changed.

The next integration step is to add a durable dispatch-intent transition to the queue, wire the scheduler to submit once, and extend the independent verifier to reconcile correlated run evidence without replaying a possibly accepted dispatch.
