# RULE-SET reference audit

- Config authority: shadowrocket/ss.conf
- RULE-SET references: 3
- Result: PASS
- External RULE-SET order: REJECT -> DIRECT -> PROXY
- Placement audit: PASS

## References

- line 1753: reject.list -> REJECT
- line 1754: direct.list -> DIRECT
- line 1755: proxy.list -> PROXY

## Generated file counts

- direct.list: 15 lines; policy DIRECT
- proxy.list: 64 lines; policy PROXY
- reject.list: 10 lines; policy REJECT

## Cross-file duplicates

- None

## Precedence-resolved overlaps

- None

## Findings

- No inconsistencies detected.

Read-only audit; no config or RULE-SET references were changed.
