# RULE-SET / ss.conf conflict synchronization

- Config: shadowrocket/ss.conf (read-only)
- Config blob SHA: c8d742ae87a75506efc15dc6effe190ae8cd6b43
- Higher-priority config rules inspected: 2216
- Published rules removed: 0
- Pending queue entries removed: 0
- Ambiguous overlaps retained for review: 7
- Restored: 0

## Removed rules
- None

## Already archived entries suppressed
- None

## Retained ambiguous overlaps
- PROXY | DOMAIN-SUFFIX,amazon.com | REVIEW | Prior DOMAIN-KEYWORD may match this candidate
- PROXY | DOMAIN-SUFFIX,blogspot.com | REVIEW | Prior DOMAIN-KEYWORD may match this candidate
- PROXY | DOMAIN-SUFFIX,blogspot.hk | REVIEW | Prior DOMAIN-KEYWORD may match this candidate
- PROXY | DOMAIN-SUFFIX,live.net | REVIEW | Prior first-match rules intersect candidate suffix scope
- PROXY | DOMAIN-SUFFIX,onedrive.com | REVIEW | Prior first-match rules intersect candidate suffix scope
- PROXY | DOMAIN-SUFFIX,pixiv.net | REVIEW | Prior DOMAIN-KEYWORD may match this candidate
- PROXY | DOMAIN-SUFFIX,thefacebook.com | REVIEW | Prior DOMAIN-KEYWORD may match this candidate

## Restoration
- None

The script never writes to shadowrocket/ss.conf. A config-conflict archive entry is not restored automatically; restoration is opt-in and rechecked against the current config.
