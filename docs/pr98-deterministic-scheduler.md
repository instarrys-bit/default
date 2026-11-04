# PR98 — Deterministic task scheduler

## Scope

The scheduler performs one bounded scheduling pass. It first recovers expired leases, then reads the GitHub-backed queue, independently verifies pending results, builds an execution plan, claims only task IDs that passed scheduler preflight, runs a reviewed Python adapter, records its completion, and invokes the independent result verifier.

The scheduler is not a daemon. The existing top-level Watchdog now invokes one bounded scheduler pass on its supported events; it does not enable any adapters or create a separate scheduler workflow.

## Fail-closed execution gates

A task is eligible only when all of the following hold:

- the task is QUEUED and its `not_before` time has arrived;
- its target is registered and orchestration is enabled for the requesting program;
- the target adapter is enabled, reviewed, and explicitly allows the requester;
- the adapter is a Python CLI adapter with valid input and output contracts;
- task input satisfies the reviewed input contract;
- the entrypoint exactly matches the registered program path and resolves inside the repository;
- the argument template contains exactly one `{task_input_file}` placeholder and uses only approved placeholders;
- shell execution is prohibited and the adapter timeout is no more than 300 seconds and shorter than the registered lease.

Only eligible task IDs are passed to the CAS claim operation. The claim callback re-reads the latest queue snapshot, so stale plans cannot claim a task that has already changed state.

## Child-process boundary

- The scheduler invokes the exact registered Python entrypoint with an argument array and `shell=False`.
- Task input is written to a temporary JSON file and deleted after execution.
- Child processes receive only a small non-secret environment allowlist. The scheduler also temporarily removes credential-like variables from its own process environment while the child runs, preventing the child from reading the parent's `/proc/.../environ` on the runner.
- The protected `modules/uu.conf` file is hashed before and after child execution. Any detected change fails the task and stops the scheduler.
- A scheduler workflow must use checkout with `persist-credentials: false`; the scheduler must receive its own narrowly scoped queue-storage token, which is never passed to child programs.

This is a defense-in-depth boundary, not a general-purpose operating-system sandbox. Only reviewed and explicitly enabled adapters may execute.

## Result handling

A child must exit successfully and emit one JSON object on stdout. The scheduler submits that object as a worker result, which moves the task to `VERIFYING`. The independent verifier then checks the registered output contract and records the verification evidence. Invalid outputs follow the bounded retry/dead-letter policy.

GitHub Actions workflow adapters are not executed by this scheduler iteration; they remain blocked until a separately reviewed workflow-dispatch adapter is implemented.

## Activation boundary

- The scheduler itself is registered but its own adapter remains disabled, unreviewed, and caller-deny-by-default.
- All existing adapters remain disabled. No program has been granted automatic execution by this PR.
- The CI workflow only runs CLI smoke checks, compilation, validators, and tests. It does not invoke `run-once`.
- No rulesets, DNS, routing policy, or `modules/uu.conf` are modified.
- Watchdog integration and recurring scheduling remain follow-up work.
