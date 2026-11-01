# RULE-SET reference audit

- Config authority: shadowrocket/ss.conf
- RULE-SET references: 3
- Result: PASS

## References

- line 653: reject.list -> REJECT
- line 1455: direct.list -> DIRECT
- line 2155: proxy.list -> PROXY

## Generated file counts

- direct.list: 32 lines; policy DIRECT
- proxy.list: 122 lines; policy PROXY
- reject.list: 22 lines; policy REJECT

## Cross-file duplicates

- None

## Precedence-resolved overlaps

- DOMAIN,adsfilebssdlbig.tx.kugou.com (REJECT) precedes DOMAIN-SUFFIX,kugou.com (DIRECT)

## Findings

- No inconsistencies detected.

Read-only audit; no config or RULE-SET references were changed.
