# RULE-SET reference audit

- Config authority: modules/uu.conf
- RULE-SET references: 3
- Result: PASS
- External RULE-SET order: REJECT -> PROXY -> DIRECT
- Placement audit: PASS

## References

- line 2038: reject.list -> REJECT
- line 2039: proxy.list -> PROXY
- line 2040: direct.list -> DIRECT

## Generated file counts

- direct.list: 147 lines; policy DIRECT
- proxy.list: 3261 lines; policy PROXY
- reject.list: 6 lines; policy REJECT

## Cross-file duplicates

- None

## Cross-policy scope overlaps (no winner selected)

- None

## Findings

- No inconsistencies detected.

Read-only audit; no config or RULE-SET references were changed.
