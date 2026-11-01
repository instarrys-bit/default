# RULE-SET reference audit

- Config authority: shadowrocket/ss.conf
- RULE-SET references: 3
- Result: PASS
- External RULE-SET order: REJECT -> PROXY -> DIRECT
- Placement audit: PASS

## References

- line 2260: reject.list -> REJECT
- line 2261: proxy.list -> PROXY
- line 2262: direct.list -> DIRECT

## Generated file counts

- direct.list: 32 lines; policy DIRECT
- proxy.list: 119 lines; policy PROXY
- reject.list: 18 lines; policy REJECT

## Cross-file duplicates

- None

## Precedence-resolved overlaps

- DOMAIN,adsfilebssdlbig.tx.kugou.com (REJECT) precedes DOMAIN-SUFFIX,kugou.com (DIRECT)

## Findings

- No inconsistencies detected.

Read-only audit; no config or RULE-SET references were changed.
