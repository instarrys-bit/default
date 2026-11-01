# RULE-SET / ss.conf conflict synchronization

- Config: shadowrocket/ss.conf (read-only)
- Config blob SHA: 36f8b88b5f3395d76bc16415d52ba8933636511a
- Higher-priority config rules inspected: 2217
- Published rules removed: 7
- Pending queue entries removed: 0
- Ambiguous overlaps retained for review: 7
- Restored: 0

## Removed rules
- cfg-c13487dfff5d4b12cd9e | PROXY | DOMAIN-SUFFIX,bing.com | config line 1081: DOMAIN-SUFFIX,cn.bing.com,DIRECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-c10acbe974988fc40b71 | PROXY | DOMAIN-SUFFIX,edgekey.net | config line 1454: DOMAIN-SUFFIX,gsp4-cn.ls.apple.com.edgekey.net,DIRECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-a6c2518c682f3dc4f6cd | PROXY | DOMAIN-SUFFIX,sfx.ms | config line 741: DOMAIN-SUFFIX,sfx.ms,DIRECT | Prior first-match rules produce a conflicting policy within suffix scope
- cfg-bda306f24b1423bda624 | REJECT | DOMAIN,ad.21cn.com | config line 782: DOMAIN-SUFFIX,21cn.com,DIRECT | Prior first-match exact/suffix domain rule
- cfg-ed5cf92b4498c7e2ad67 | REJECT | DOMAIN,adbehavior.ximalaya.com | config line 1225: DOMAIN-SUFFIX,ximalaya.com,DIRECT | Prior first-match exact/suffix domain rule
- cfg-78411fbb3c84a334d9ef | REJECT | DOMAIN,adsehera.ximalaya.com | config line 1225: DOMAIN-SUFFIX,ximalaya.com,DIRECT | Prior first-match exact/suffix domain rule
- cfg-fb54aeabab750721e8ea | REJECT | DOMAIN,adwbs.ximalaya.com | config line 1225: DOMAIN-SUFFIX,ximalaya.com,DIRECT | Prior first-match exact/suffix domain rule

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
