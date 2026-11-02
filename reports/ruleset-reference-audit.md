# RULE-SET reference audit

- Config authority: shadowrocket/ss.conf
- RULE-SET references: 3
- Result: PASS
- External RULE-SET order: REJECT -> PROXY -> DIRECT
- Placement audit: PASS

## References

- line 1898: reject.list -> REJECT
- line 1899: proxy.list -> PROXY
- line 1900: direct.list -> DIRECT

## Generated file counts

- direct.list: 133 lines; policy DIRECT
- proxy.list: 246 lines; policy PROXY
- reject.list: 6 lines; policy REJECT

## Cross-file duplicates

- None

## Cross-policy scope overlaps (no winner selected)

- None

## Findings

- No inconsistencies detected.

Read-only audit; no config or RULE-SET references were changed.
