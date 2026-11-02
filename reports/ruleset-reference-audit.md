# RULE-SET reference audit

- Config authority: shadowrocket/ss.conf
- RULE-SET references: 3
- Result: PASS
- External RULE-SET order: REJECT -> PROXY -> DIRECT
- Placement audit: PASS

## References

- line 1718: reject.list -> REJECT
- line 1719: proxy.list -> PROXY
- line 1720: direct.list -> DIRECT

## Generated file counts

- direct.list: 216 lines; policy DIRECT
- proxy.list: 205 lines; policy PROXY
- reject.list: 10 lines; policy REJECT

## Cross-file duplicates

- None

## Precedence-resolved overlaps

- None

## Findings

- No inconsistencies detected.

Read-only audit; no config or RULE-SET references were changed.
