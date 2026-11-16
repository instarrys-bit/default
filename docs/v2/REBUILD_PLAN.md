# V2 Rebuild and V1 Data Preservation Plan

## Execution policy

This plan authorizes a non-destructive parallel rebuild. It does not authorize deletion, renaming, rewriting or disabling of V1 production files or workflows during the foundation phase.

## Phase 0 — freeze and preserve (completed)

- [x] Create `archive/v1-pre-v2-2026-11-17` from the current `main` snapshot.
- [x] Create `v2/rebuild-foundation-2026-11-17` from the same baseline.
- [x] Preserve all tracked V1 files in the archive branch.
- [x] Record every tracked file path, size and blob SHA in the V1 inventory.
- [x] Record V1 queue revision and lease counts without importing them into V2.
- [x] Keep `modules/uu.conf` untouched.

## Phase 1 — contracts and schemas

- [ ] Define Storage Management APIs and schemas first: event append, projection read, task claim/complete, resource lease acquire/release, artifact stage, release commit, audit query.
- [ ] Define Watchdog dispatch and recovery contracts.
- [ ] Define Production stage contracts and artifact envelopes.
- [ ] Define Dashboard read models.
- [ ] Define global idempotency, fencing, SHA-CAS and failure semantics.
- [ ] Define a machine-enforced write allowlist; `modules/uu.conf` is denylisted for all automation identities.

## Phase 2 — Storage Management first implementation

- [ ] Implement append-only V2 event log and rebuildable projections.
- [ ] Bootstrap only from an explicitly reviewed empty V2 seed.
- [ ] Implement separate task and resource lease state machines.
- [ ] Implement staging zones for imported V1 data.
- [ ] Implement content-addressed artifacts and immutable release records.
- [ ] Implement CAS writes, idempotency and independent read-back verification.

## Phase 3 — Production

- [ ] Port source discovery and collection as isolated workers.
- [ ] Port deterministic filtering/assessment without AI review.
- [ ] Add provenance and confidence evidence to every candidate.
- [ ] Add deterministic duplicate and policy-conflict handling.
- [ ] Stage release outputs before committing a release.
- [ ] Publish only the three ruleset files and explicitly approved metadata.

## Phase 4 — Watchdog and Dashboard

- [ ] Implement Watchdog as the sole top-level scheduler.
- [ ] Recovery requests must pass through Storage Management; Watchdog cannot mutate storage internals.
- [ ] Dashboard reads only verified Storage Management projections.
- [ ] Show unknown/missing historical state as unavailable, never infer success.

## Phase 5 — migration and validation

- [x] Verify all 239 V1 inventory paths against the frozen archive Git tree (exact blob SHA and byte size; zero missing, extra or mismatched entries). See ARCHIVE_INTEGRITY_2026-11-17.md.
- [ ] Migrate data in batches to V2 staging, retaining original path, blob SHA, source, timestamp and classification.
- [ ] Revalidate lineage, duplicates, conflicts and freshness before promotion.
- [ ] Keep uncertain and rejected data in quarantine/archive.
- [ ] Run tests for concurrency, crashes, retries, expired leases, duplicate delivery, partial publication and rollback.
- [ ] Verify `modules/uu.conf` blob SHA is unchanged and all automation write paths deny it.
- [ ] Shadow-run V2 against V1 outputs and compare results.
- [ ] Cut over only after evidence-based acceptance; retain V1 archive.

## Initial V1 assets discovered

- `data/candidates.json` — 12,139,598 bytes.
- `data/domain_candidates.json` — 1,800,310 bytes.
- `data/primary_snapshot.txt` — 1,046,646 bytes.
- `data/secondary_snapshot.txt` — 4,080,086 bytes.
- `data/source_snapshots/**` — preserved source snapshots.
- `reports/**` — discovery, assessment, lineage, audit and lifecycle reports.
- `rulesets/**` — published DIRECT/PROXY/REJECT outputs, manifests, queues and lifecycle history.
- `automation/task_queue.json` — V1 queue snapshot at revision 877 (160 tasks, 23 resource leases).
- `reports/automation/task-queue-archive-2026-11-05.json` — older queue archive.
- `modules/uu.conf` — user-owned configuration; read-only to automation.

This summary is not a claim that every item is valid for automatic migration. The full tracked-file inventory is `legacy-v1-inventory.json`.
