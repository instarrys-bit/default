# V2 Artifact Staging

## Immutable artifact model

- artifact_id: SHA-256 of the complete logical content.
- record_id: SHA-256 of the canonical manifest, including provenance.
- chunk_id: SHA-256 of each immutable content chunk.

The artifact staging module provides deterministic manifests, content-addressed chunk storage, atomic no-overwrite writes, manifest identity checks, chunk read-back checks, and end-to-end reassembly verification. Repeated content is deduplicated at the chunk layer; different provenance records remain independently addressable. A logical artifact is capped at 50 MiB and each chunk is capped at 8 MiB.

The filesystem adapter deliberately performs no garbage collection and never overwrites an existing object. Corrupt or conflicting objects fail closed. Retention and deletion require a separate audited lifecycle operation and are not part of staging.

## Persistence boundary

The backend-neutral CAS store can use either the local filesystem adapter or the GitHub Contents API adapter. The GitHub adapter creates immutable objects under the exact Storage Management allowlist path storage/v2/artifacts/sha256/<digest>, without supplying an update SHA; concurrent duplicate creates are reconciled by reading back and comparing bytes. It writes all chunks first and the canonical manifest last, so a missing manifest means the artifact is not committed. Each object is a separate Git commit, so Storage Management must batch work and respect GitHub API rate limits. The local filesystem adapter remains useful for tests and isolated staging, but an ephemeral CI workspace is never authoritative.

The GitHub adapter is implemented but not activated by any production workflow. Enabling it requires the V2 epoch, a Storage Management identity, and a verified release gate. Artifacts are not promoted merely because staging succeeded. Production must still pass schema validation, provenance checks, duplicate/conflict checks, release preparation, publication, and independent post-publication verification.

## Limits

- Default chunk size: 4 MiB; maximum: 8 MiB.
- Maximum logical artifact size: 50 MiB.
- Empty artifacts are represented by one empty chunk.
- Each chunk and complete artifact are verified with SHA-256.
- Manifest record IDs bind content identity to provenance and producer metadata.
