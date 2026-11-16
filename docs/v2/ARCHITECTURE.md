# V2 Architecture Baseline

Status: design baseline for the parallel rebuild. V1 production remains untouched until V2 passes acceptance.

## Goal

Rebuild the automation architecture around four bounded subsystems while preserving all V1 production data in an immutable Git snapshot.

## Four subsystems

1. **Watchdog (control plane)** — the sole top-level scheduler and lifecycle supervisor. It dispatches work, detects timeout/failure, requests lease recovery through Storage Management, and verifies end-to-end completion. It does not directly edit production data.
2. **Dashboard (read-only presentation plane)** — reads verified projections and evidence from Storage Management. It displays queue/task/lease status, production runs, releases, audit results and exceptions. It does not directly mutate queue, production or configuration state.
3. **Production (execution plane)** — source discovery/collection, deterministic filtering and assessment, candidate construction, conflict checking, ruleset build, publication request and post-publication validation. It has no direct authority to mutate queue internals or arbitrary repository paths.
4. **Storage Management (data plane + persistence plane)** — the single owner of durable data and state: V2 queue/event log, task and resource leases, source snapshots, candidates, assessments, review cursors, ruleset repository, release manifests, SHA/version records, audit evidence, recovery records and read projections for Dashboard.

## Data ownership

Storage Management contains the complete data plane. There is no fifth data-plane subsystem.

Production submits validated artifacts and publication intents to Storage Management. Storage Management validates schema, provenance, idempotency, allowed path and expected SHA before accepting writes. Watchdog requests state transitions through Storage Management. Dashboard consumes read-only projections.

## Immutable safety boundaries

- `modules/uu.conf` is user-managed. V2 automation has read-only access; it must never write, replace, regenerate, reformat or delete it.
- Production publication is restricted to exactly `rulesets/direct.list`, `rulesets/proxy.list`, `rulesets/reject.list` plus explicitly enumerated release manifests/lifecycle metadata.
- No retired writer guard and no `fenced_file_writer.py`.
- No AI review flow. Filtering/review gates are deterministic and evidence-based.
- Preserve SHA-CAS, task leases, resource fencing, idempotency keys and independent post-write verification.
- A task lease and a resource lease are distinct state machines and must be verified/recovered independently.
- Unknown historical task outcomes remain unknown; do not replay them automatically.

## V1 preservation and V2 isolation

- V1 is frozen at commit `c6c95b1282826dbc9fb74858f707001e874f7459` on branch `archive/v1-pre-v2-2026-11-17`.
- The archive branch preserves the full tracked V1 repository snapshot. `legacy-v1-inventory.json` records every tracked path, byte size and Git blob SHA.
- V1 data is retained as source material and audit history, not presumed valid/current production input.
- V2 starts with a new queue epoch and a separately initialized empty seed. Do not import V1 queue statuses or leases.
- Migration uses staging: inventory -> hash verification -> schema validation -> duplicate/conflict analysis -> lineage/evidence review -> explicit acceptance. Rejected or uncertain records remain archived/quarantined.
- Existing `data/**`, `reports/**`, `rulesets/**`, `sources/**` and historical queue records are not deleted as part of this foundation phase.

## Release and cutover model

1. Build V2 in parallel on its own branch.
2. Keep V1 production workflows unchanged during design and implementation.
3. Migrate data into V2 staging, never directly into live outputs.
4. Run deterministic tests, concurrency tests, recovery tests, output-scope tests and independent publication verification.
5. Run a controlled shadow period and compare results.
6. Cut over only after acceptance evidence is recorded. V1 remains archived and recoverable.

## Acceptance gates

- Storage bootstrap/read/append and SHA-CAS concurrency.
- Task lease and resource lease expiry/recovery.
- Watchdog supervision without direct data writes.
- Source discovery -> deterministic assessment handoff.
- Candidate provenance and duplicate/conflict handling.
- Ruleset publication limited to the explicit allowlist.
- Post-publication remote content and SHA verification.
- Dashboard values match Storage Management projections.
- Automated attempts to write `modules/uu.conf` and unrelated paths are denied and tested.
- Rollback restores the previous verified ruleset release without altering user configuration.

## V1 current-state note

The checked-in V1 queue document is revision 877 with 160 tasks and 23 resource leases. The queue pointer names issue #571 as its index; issue #423 is a read-only historical issue-comment epoch after reaching its 2,500-comment ceiling. These facts describe V1 only and are not V2 state.
