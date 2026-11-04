# Operations

## Start with status reports

Use the report for the subsystem under investigation:

- `reports/project-status.md` and `reports/project-status.json` — policy counts, capacity, queue, source health, review status, lifecycle milestones, configuration baseline, and recovery inventory.
- `reports/lifecycle/latest.md` and `latest.json` — latest lifecycle audit and recovery candidates.
- `reports/ruleset-config-conflict-sync.md` — configuration-conflict synchronization and recovery IDs.
- `reports/source-discovery.md` and `reports/source-assessment.md` — discovery and parser/policy assessment.
- `reports/source-lineage-audit.json` — source ancestry findings.
- `reports/source-candidate-matrix.md` — publisher counts, evidence eligibility, overlap, and blockers.
- `reports/policy-source-overlap.md` — same-policy overlap and cross-policy conflict signals.
- `reports/direct-proxy-source-research.md` — source provenance research.

Reports are generated evidence. They do not authorize bypassing policy or safety gates.

## Common failure classes

### Network and fetch errors

Distinguish transient errors from permanent failures. Only configured transient statuses and timeouts receive bounded retries. Permanent client errors, malformed content, and policy failures are not retryable network conditions.

### Parser and format errors

Check the source's registered parser and verify that fetched bytes match the assessed snapshot. Unsupported rule types must be ignored or held, never converted into domain entries by guesswork.

### Policy conflicts

A domain with current evidence under multiple policies remains isolated. Do not resolve conflicts by source ordering, correlated-source majority, or domain-name inference.

### Main-configuration baseline mismatch

Treat an unexplained change to `modules/uu.conf` as an integrity failure. Do not overwrite the file or silently update the baseline. Confirm owner approval and use the designated baseline process.

### Capacity reached

A full ruleset pauses publication, not candidate collection or review. Inspect the pending queue and lifecycle report. Do not delete existing rules simply to make room.

### Device behavior differs from static validation

Static checks cannot prove that Shadowrocket, DNS paths, apps, or system services behave as expected. Reproduce on the target device and record the observation separately from static validation.
## Configuration-conflict recovery

Configuration-conflict removals are tracked separately from lifecycle deletions. Review `rulesets/config_conflict_archive.json` and the recovery IDs in `reports/ruleset-config-conflict-sync.md`. If a removal is confirmed to be erroneous, provide its ID through `restore_conflict_ids` in the manual GitHub Actions workflow. The restore process rechecks the current `uu.conf`, skip-proxy entries, published rules, and pending queue for cross-policy overlap; unsafe restorations are rejected.

Lifecycle deletion recovery uses `restore_ids` instead. Never substitute one recovery ID type for the other.
