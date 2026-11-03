# PR94 — GitHub-backed persistent task queue storage

## Scope

This change introduces a GitHub Contents API storage adapter for the existing
`automation/task_queue.json` document. It is a persistence primitive, not an
execution engine.

## Concurrency contract

- Every write requires the exact blob SHA returned by a preceding read.
- A stale SHA is treated as a compare-and-swap conflict; blind overwrite is
  prohibited.
- On conflict, the caller re-reads the latest document and re-applies its
  deterministic, side-effect-free mutation.
- Enqueue operations must retain the existing idempotency-key semantics.
- Retry is limited to explicit content-SHA conflicts. Permission errors,
  malformed data, timeouts, and other API failures fail closed.
- No token values are logged or included in exception messages.

## Operational boundaries

- The current local `task_queue_runtime.py` remains a local single-writer
  implementation until a later PR integrates this adapter into the worker.
- All remote writers must use SHA-guarded updates; GitHub Actions concurrency
  groups remain useful for reducing contention but are not the correctness
  mechanism.
- This adapter does not provide distributed leases, workflow dispatch,
  independent completion verification, or watchdog recovery. Those remain
  separate follow-up work.
- No adapter is enabled by this PR. No ruleset or `shadowrocket/ss.conf`
  content is changed.

## Validation

The unit tests mock the GitHub API and cover read, guarded write, stale-SHA
re-read/replay, conflict exhaustion, non-conflict failures, and no-op writes.
A real GitHub token and concurrent Actions run are required for live integration
validation and are intentionally not claimed by these unit tests.
