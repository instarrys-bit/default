# PR97 — Independent task result verification

## State transition

The remote worker no longer marks a successful task as `SUCCEEDED`. After lease-authenticated completion, it stores the result and moves the task to `VERIFYING`. A separate verifier then evaluates that result and, only when the target program has an enabled, reviewed adapter with an explicit output contract, moves the task to `SUCCEEDED`.

Invalid results are recorded as verification failures and follow the registered bounded retry/backoff policy, ending in `DEAD_LETTER` when attempts are exhausted. Missing or unreviewed contracts are reported as blocked and leave the task in `VERIFYING`; absence of a contract is not treated as success or as proof of a bad result.

## Deterministic contract validation

The verifier implements a deliberately limited JSON Schema subset: type, required properties, properties, additionalProperties, items, enum, const, string lengths, numeric bounds, and array lengths. Unsupported schema keywords and malformed schema definitions fail closed. The contract itself must come from the target program's execution adapter and must be enabled and marked `reviewed`.

The verifier records its program ID, timestamp, contract digest, and pass/fail status on the task. The verification operation is persisted through the GitHub SHA-CAS store. Its mutation callback is replay-safe: all report accumulators are local to each invocation.

## Boundaries

- No program adapter is enabled by this PR.
- No program receives a caller allowlist or automatic dispatch authorization.
- Existing local queue runtime compatibility is preserved; this two-phase success gate is applied to the GitHub-backed remote runtime.
- The verifier checks output structure against an approved contract. It does not prove that an external side effect occurred; future adapters must define trustworthy evidence requirements where that matters.
- No rulesets, routing policy, DNS settings, or `modules/uu.conf` are modified.
- Scheduler and Watchdog integration remain separate follow-up work.

## Validation

Tests cover valid and invalid results, missing-contract blocking, unsupported schema keywords, nested arrays, additional properties, and the remote runtime's transition to `VERIFYING`. CI runs registry and adapter inventory validation, queue contract validation, CLI smoke checks, compilation, and the full test suite.
