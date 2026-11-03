# PR96 — GitHub-backed remote task queue runtime

## Scope

This change adds a remote runtime that stores the existing task queue document in GitHub Contents API storage through `GitHubContentsQueueStore`. Every mutation uses the store's SHA compare-and-swap loop. On a stale SHA, the store re-reads and replays the mutation callback; non-conflict API failures remain fail-closed.

The runtime preserves the task contract and state machine already used by the local queue runtime:

- idempotent enqueue with payload mismatch rejection;
- priority-ordered claim;
- owner-bound, unguessable lease token and expiry;
- lease-checked success or failure completion;
- bounded retry with backoff and dead-letter transition;
- expired-lease recovery;
- independent validation of the existing queue schema before and after every mutation.

## Deterministic CAS replay

Identifiers and lease tokens are generated before entering the mutation callback. The callback itself only derives a candidate document from the snapshot and captured immutable inputs, so a stale-SHA replay does not generate a different task identity or lease credential.

## Invocation

The CLI requires a repository identity and a GitHub token with narrowly scoped Contents read/write permission. The token is read by the storage library from the environment and is never printed.

Examples:

```sh
export GITHUB_TOKEN='...'
python scripts/remote_task_queue_runtime.py --repository owner/repo --branch main validate
python scripts/remote_task_queue_runtime.py --repository owner/repo --branch main enqueue --task-json task.json
python scripts/remote_task_queue_runtime.py --repository owner/repo --branch main claim --worker-id worker-01
```

Completion requires the task ID, worker ID, lease token, and exactly one result or error JSON file. Expired leases can be recovered with `recover-expired`.

## Activation and safety boundaries

- The program and adapter are registered, but orchestration remains disabled.
- The adapter is unreviewed, has no input/output contract, and has an empty caller allowlist.
- This PR does not dispatch programs or start background workers.
- This PR does not grant GitHub permissions; the calling workflow or operator must provide them.
- The runtime must only write the queue document path supplied to the storage store. It does not read or modify `shadowrocket/ss.conf`, routing rules, or DNS settings.
- A successful queue-state write is not proof that the target program executed successfully. Completion is a separate lease-authenticated state transition; independent task-result verification and scheduler/Watchdog integration remain follow-up work.

## Validation

Unit tests cover idempotency, priority claims, lease ownership, completion, retry/dead-letter behavior, expired-lease recovery, and no-op operations. CI performs a CLI smoke check, Python compilation, registry/adapter validation, queue-contract validation, and the full test suite.
