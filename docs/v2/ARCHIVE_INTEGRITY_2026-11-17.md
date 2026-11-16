# V1 Archive Integrity Verification — 2026-11-17

## Result

- Archive branch: archive/v1-pre-v2-2026-11-17
- Frozen archive commit: c6c95b1282826dbc9fb74858f707001e874f7459
- Actual Git tree SHA: 721f9bd67d6e6bd9dd55953748794417211628b8
- Tracked files in inventory: 239
- Tracked files in archive tree: 239
- Total bytes: 280,466,056
- Missing paths: 0
- Unexpected paths: 0
- Blob SHA mismatches: 0
- Byte-size mismatches: 0

Every inventory path, Git blob SHA-1 and byte size matched the archive commit's recursive Git tree. Git blob SHA is calculated by Git over the canonical blob object framing and therefore binds the archived file bytes; the recursive tree comparison also confirms exact path coverage.

## Metadata correction

The initial V1 inventory and migration manifest incorrectly recorded the archive commit SHA in the tree_sha field. The actual tree SHA is 721f9bd67d6e6bd9dd55953748794417211628b8. The V2-side inventory and migration manifest are corrected to this actual tree SHA. The frozen archive commit and all 239 archived files remain unchanged.

## Scope and limits

This check verifies archive identity, path coverage, Git blob SHA and byte size. It does not claim that all JSON schemas, source lineage, freshness, duplicate/conflict status or ruleset eligibility have been accepted. The 66 migration candidates remain DISCOVERED_NOT_IMPORTED and QUARANTINED_PENDING_VALIDATION. No historical task state or active lease is imported, and no source data is promoted or published.

The verification can be repeated with scripts/verify_v1_archive_inventory.py.
