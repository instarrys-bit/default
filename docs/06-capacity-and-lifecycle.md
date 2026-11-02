# Capacity and Lifecycle

## Global capacity

The combined published total across DIRECT, PROXY, and REJECT has a hard ceiling of 30,000 unique rules.

When otherwise approved additions exceed available capacity:

- Retain existing published rules.
- Store eligible additions in the persistent `rulesets/pending_queue.json`.
- Promote queued entries in priority/FIFO order as capacity becomes available.
- Continue discovery and deterministic review; the cap pauses publication, not intake or queue storage.

The output directory is restricted to `direct.list`, `proxy.list`, and `reject.list`.

## Lifecycle milestones

Run lifecycle review at every 5,000-rule published-count milestone: 5,000, 10,000, 15,000, 20,000, 25,000, and 30,000. A milestone remains pending until its audit succeeds. At 30,000 published rules, also run a lifecycle audit every 30 days.

## Conservative deletion

Do not delete rules merely because a source stops publishing them, lineage metadata changes, or one resolver returns an error or NXDOMAIN.

An exact `DOMAIN` host is eligible only after both Cloudflare and Google DNS-over-HTTPS resolvers return NXDOMAIN for both A and AAAA queries on two separate observations at least 30 days apart, with no intervening DNS recovery.

Retain `DOMAIN-SUFFIX` rules. A suffix root may lack DNS records while valid subdomains remain active. Major technology, cloud, CDN, identity, and Chinese platform suffixes are protected from automatic deletion.

Missing evidence, resolver errors, timeouts, one NXDOMAIN observation, source disappearance, or lineage changes never authorize deletion.

## Archive and recovery

Every lifecycle removal is archived with its original policy, rule, timestamps, and evidence in `rulesets/deletion_archive.json`. Per-run reports are written to `reports/lifecycle/latest.md` and `latest.json`.

To restore an entry, use its recovery ID from the report with the manual workflow's `restore_ids` input. Restore to the original policy when capacity permits; otherwise place it at the front of the pending queue. A restored entry must not be deleted again during the same run.

## Configuration-conflict recovery

Configuration-conflict removals use a separate archive and recovery input. Before restoring, recheck the current `ss.conf`, skip-proxy behavior, published rules, and pending queue for cross-policy overlap. Do not mix configuration-conflict recovery IDs with lifecycle `restore_ids`.

## Change accounting

The manifest's `rule_lifecycle` section records per-policy counts before and after a build, additions/removals, before/after SHA-256 values, and up to ten change examples. This is audit data; it does not relax review or deletion requirements.