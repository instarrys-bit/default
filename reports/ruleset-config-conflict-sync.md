# RULE-SET / ss.conf conflict synchronization

- Config: shadowrocket/ss.conf (read-only)
- Config blob SHA: 1e8763924c0ce4cf9d1c0ac93676105645302e9c
- Higher-priority config rules inspected: 1708
- Published rules removed: 0
- Pending queue entries removed: 0
- Ambiguous overlaps retained for review: 1
- Restored: 0

## Removed rules
- None

## Already archived entries suppressed
- None

## Retained ambiguous overlaps
- PROXY | DOMAIN-SUFFIX,thefacebook.com | REVIEW | Prior DOMAIN-KEYWORD may match this candidate

## Restoration
- None

The script never writes to shadowrocket/ss.conf. A config-scope archive entry is not restored automatically; restoration is opt-in and rechecked against all exact/suffix overlaps and skip-proxy entries.
