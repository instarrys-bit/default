# RULE-SET reference audit

- Config authority: shadowrocket/ss.conf
- RULE-SET references: 3
- Result: PASS
- External RULE-SET order: REJECT -> DIRECT -> PROXY
- Placement audit: PASS

## References

- line 1993: reject.list -> REJECT
- line 1994: direct.list -> DIRECT
- line 1995: proxy.list -> PROXY

## Generated file counts

- direct.list: 15 lines; policy DIRECT
- proxy.list: 63 lines; policy PROXY
- reject.list: 10 lines; policy REJECT

## Cross-file duplicates

- None

## Precedence-resolved overlaps

- None

## Findings

- No inconsistencies detected.

Read-only audit; no config or RULE-SET references were changed.
