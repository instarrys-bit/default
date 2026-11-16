# V2 Production Source Handoff

## Reuse boundary

The existing V1 Source Discovery and Source Assessment workflows already emit immutable Actions artifacts with provenance proofs. V2 reuses those exact outputs instead of rerunning discovery or assessment.

- Discovery proof binds workflow name, run ID, head commit, logical document path and logical document digest.
- Assessment proof binds the canonical Watchdog task ID, independently verified SUCCEEDED status, non-activation evidence, exact Discovery predecessor, producer workflow run/head SHA, per-file SHA-256 manifest and manifest digest.
- The V2 importer independently revalidates both proof chains and the complete Assessment artifact file set before staging.

## Staging

The importer stages each exact file into the V2 content-addressed artifact store, preserving path, producer, source revision, run ID and task provenance. It writes one immutable source-handoff manifest last. The handoff manifest explicitly records activation_count=0 and publication_status=NOT_PUBLISHED.

The import is idempotent: content chunks deduplicate by SHA-256; provenance-specific manifest records remain independently addressable. Partial failures may leave unreferenced immutable chunks, but no handoff manifest is committed and no production task is advanced.

## Activation gate

The CLI is read-only by default. Durable writes require all of the following:
- explicit --execute;
- STORAGE_MANAGEMENT_TOKEN;
- V2_STORAGE_EPOCH_ID matching an already initialized storage/v2/state.json;
- a valid V2 event-sourced state projection;
- the exact verified Discovery and Assessment roots and provenance identifiers.

No workflow invokes this importer yet. It does not create an epoch, import V1 queue/lease state, activate candidates, publish rulesets, or modify modules/uu.conf.
