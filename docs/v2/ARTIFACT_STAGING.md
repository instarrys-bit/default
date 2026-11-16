# V2 Artifact Staging

## Immutable artifact model

- artifact_id: SHA-256 of the complete logical content.
- record_id: SHA-256 of the canonical manifest, including provenance.
- chunk_id: SHA-256 of each immutable content chunk.

The artifact staging module provides deterministic manifests, content-addressed chunk storage, atomic no-overwrite writes, manifest identity checks, chunk read-back checks, and end-to-end reassembly verification. Repeated content is deduplicated at the chunk layer; different provenance records remain independently addressable.

The filesystem adapter deliberately performs no garbage collection and never overwrites an existing object. Corrupt or conflicting objects fail closed. Retention and deletion require a separate audited lifecycle operation and are not part of staging.

## Persistence boundary

The filesystem adapter is a backend primitive, not permission to use an ephemeral CI workspace as durable storage. Production must mount a durable volume or provide an object-store adapter with equivalent conditional-create, read-after-write, and immutable-key semantics. A GitHub Actions workspace may be used only for temporary verification or transport.

Artifacts are not promoted merely because staging succeeded. Production must still pass schema validation, provenance checks, duplicate/conflict checks, release preparation, publication, and independent post-publication verification.

## Limits

- Default chunk size: 4 MiB; maximum: 8 MiB.
- Empty artifacts are represented by one empty chunk.
- Each chunk and complete artifact are verified with SHA-256.
- Manifest record IDs bind content identity to provenance and producer metadata.
