# GitHub-Only Candidate Pool Storage

## Capacity contract

- Candidate intake pool: hard maximum **30,000,000** unique records.
- Published rules: hard maximum **30,000 combined** across DIRECT, PROXY, and REJECT.
- The three policy outputs remain the only publishable routing classes.
- `shadowrocket/ss.conf` remains user-owned and read-only to this automation.

## Storage layout

The candidate pool is stored in this repository, not in an external service:

```
data/candidate_pool/
  manifest.json
  shards/
    part-000000.ndjson.gz
    part-000001.ndjson.gz
    ...
```

Shards are immutable, gzip-compressed NDJSON. The manifest stores record counts and SHA-256 checksums. The default shard target is 50,000 records; files are split into new shards on subsequent appends. The implementation uses deterministic JSON serialization and gzip timestamps for reproducible shard bytes.

## Processing guarantees

- Intake is append-only; old shards are not rewritten by ingestion.
- Exact duplicate records are detected by SHA-256 of canonical JSON using a disk-backed SQLite index rebuilt on the GitHub Actions runner. The index is temporary and is not committed.
- The 30-million cap is checked before admitting each unique record; overflow fails closed.
- Manifest writes are atomic. A failed run may leave an unreferenced shard file, but it cannot become visible in the manifest and can be safely reconciled by a later integrity check.
- Verification checks each shard checksum, decompresses each record, and reconciles shard counts against the manifest.

## Important rollout boundary

This storage primitive is the first migration layer, not proof that the entire pipeline can yet process 30 million records. Existing candidate and review workflows still consume legacy JSON files in parts of the pipeline. Do not delete or replace `data/candidates.json`, `data/domain_candidates.json`, `sources/domain_reviews.json`, or source snapshots until every consumer has been migrated to streaming/shard iteration and a full-scale rehearsal has passed.

GitHub repository storage and Git history still have practical size and bandwidth limits. Sharding prevents individual oversized files and reduces peak memory; it does not make 30 million records free or guarantee that a single repository can accommodate an arbitrarily large pool. Monitor repository size, Actions runtime, artifact sizes, and clone/fetch time. Stop intake rather than pruning history or deleting evidence when any platform limit is approached.

## Commands

Append NDJSON records:

```bash
python3 scripts/sharded_candidate_store.py ingest-ndjson \
  --root data/candidate_pool \
  --input incoming.ndjson \
  --shard-records 50000 \
  --max-candidates 30000000
```

Verify the complete store:

```bash
python3 scripts/sharded_candidate_store.py verify --root data/candidate_pool
```
