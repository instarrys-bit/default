# Four-System Operating Contract

## Operating model

The project has exactly four operational systems:

1. **Watchdog** — schedules production work, monitors workflow health, detects stalled or failed runs, and dispatches recovery.
2. **Production** — discovers sources, collects candidates, filters, classifies, validates, builds, and publishes DIRECT, PROXY, and REJECT rules automatically.
3. **Storage Management** — owns the durable task queue, leases, checkpoints, and runtime incident state.
4. **Dashboard** — read-only visibility into system health, queue state, releases, and runtime exceptions.

## Human involvement

Human review is limited to automation runtime exceptions, including stalled tasks, repeated workflow failures, queue/CAS corruption, expired or conflicting leases, failed output verification, and failed publication.

There is no human approval stage for ordinary rule candidates. DIRECT, PROXY, and REJECT processing is automatic. Automated syntax, provenance, duplicate, scope, conflict, freshness, and publication-integrity checks remain machine-enforced controls; they are not human review gates. The REJECT recheck queue is an automated re-evaluation queue, not a manual approval queue.

## Queue state

The legacy queue state has been cleared. The active repository JSON queue starts at revision 0 with zero tasks, zero resource leases, and zero manual-authorization records. Historical tasks are not imported, replayed, or retained as active queue state. New work is created only by the current Watchdog/Production flow and persisted by Storage Management through Contents API SHA-CAS with read-after-write verification.

The old Issue-comment queue backend and its index are retired. GitHub Issues are not used as the durable task queue.

## Write boundaries

- `modules/uu.conf` is user-owned and read-only to automation.
- Modules and their scripts are not production write targets.
- Production publishes only the explicitly allowlisted `rulesets/**` outputs and release metadata.
- Storage Management owns queue, lease, checkpoint, and incident persistence.
- Dashboard has no write authority.

## Acceptance

The system is not considered fully healthy merely because workflows start. Acceptance requires successful unattended discovery-to-publication runs, verified queue transitions, lease recovery, bounded retries, post-publication verification, and automatic recovery from runtime failures. Human attention is reserved for exceptions the automation cannot safely resolve.
