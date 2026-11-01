# Automated source assessment

- Rule-list files assessed: **50**
- This stage checks syntax and explicit policy claims only. It never activates sources.
- Keyword, IP/CIDR and ASN rules are counted as ignored; they are never converted into domains.

| Repository | Parser candidate | Policy candidate | Domain entries | Drift | Evidence |
|---|---|---|---:|---|---|
| blackmatrix7/ios_rule_script | unsupported_or_too_small | — | 0 | unchanged | none |
| blackmatrix7/ios_rule_script | unsupported_or_too_small | — | 0 | unchanged | none |
| Loyalsoldier/v2ray-rules-dat | domain-only | — | 109578 | unchanged | ambiguous |
| Loyalsoldier/v2ray-rules-dat | domain-only | — | 26487 | unchanged | ambiguous |
| Loyalsoldier/v2ray-rules-dat | fetch_or_validation_error | — | 0 | unavailable | none |
| Hackl0us/SS-Rule-Snippet | shadowrocket-domain-rules | — | 118 | unchanged | ambiguous |
| Hackl0us/SS-Rule-Snippet | shadowrocket-domain-rules | — | 272 | unchanged | none |
| ACL4SSR/ACL4SSR | shadowrocket-domain-rules | DIRECT | 605 | unchanged | README_policy_reference |
| ACL4SSR/ACL4SSR | shadowrocket-domain-rules | PROXY | 6766 | unchanged | README_policy_reference |
| ACL4SSR/ACL4SSR | shadowrocket-domain-rules | PROXY | 306 | unchanged | README_policy_reference |
| sve1r/Rules-For-Quantumult-X | quantumult-domain-rules | — | 249 | unchanged | ambiguous |
| sve1r/Rules-For-Quantumult-X | quantumult-domain-rules | PROXY | 574 | unchanged | explicit_third_field |
| sve1r/Rules-For-Quantumult-X | unsupported_or_too_small | — | 16 | unchanged | ambiguous |
| gatework/surge-rules | domain-only | — | 110088 | unchanged | ambiguous |
| gatework/surge-rules | domain-only | PROXY | 4451 | unchanged | README_policy_reference |
| gatework/surge-rules | domain-only | — | 27254 | unchanged | ambiguous |
| Clash-FX/cn-apps-direct-domains | shadowrocket-domain-rules | DIRECT | 120 | unchanged | explicit_third_field |
| Jovanykoch/rules | domain-only | — | 4367 | unchanged | ambiguous |
| Jovanykoch/rules | domain-only | DIRECT | 6751 | unchanged | README_policy_reference |
| Jovanykoch/rules | domain-only | — | 957 | unchanged | ambiguous |
| GMOogway/shadowrocket-rules | unsupported_or_too_small | — | 0 | unchanged | none |
| PaPerseller/chn-iplist | unsupported_or_too_small | — | 0 | unchanged | none |
| PaPerseller/chn-iplist | unsupported_or_too_small | REJECT | 0 | content_changed_baseline_schema_unavailable | README_policy_reference |
| PaPerseller/chn-iplist | unsupported_or_too_small | REJECT | 0 | unchanged | README_policy_reference |
| PaPerseller/chn-iplist | unsupported_or_too_small | REJECT | 0 | unchanged | README_policy_reference |
| PaPerseller/chn-iplist | unsupported_or_too_small | REJECT | 0 | unchanged | README_policy_reference |
| PaPerseller/chn-iplist | unsupported_or_too_small | DIRECT | 1 | unchanged | README_policy_reference |
| PaPerseller/chn-iplist | unsupported_or_too_small | — | 0 | unchanged | none |
| PaPerseller/chn-iplist | unsupported_or_too_small | — | 0 | unchanged | none |
| PaPerseller/chn-iplist | unsupported_or_too_small | PROXY | 14 | unchanged | README_policy_reference |
| PaPerseller/chn-iplist | unsupported_or_too_small | REJECT | 11 | unchanged | README_policy_reference |
| PaPerseller/chn-iplist | unsupported_or_too_small | — | 0 | unchanged | none |
| Vann-Dev/proxy-list | unsupported_or_too_small | PROXY | 1 | unchanged | README_policy_reference |
| Vann-Dev/proxy-list | unsupported_or_too_small | PROXY | 1 | unchanged | README_policy_reference |
| tickmao/Rules | unsupported_or_too_small | — | 0 | unchanged | none |
| tickmao/Rules | unsupported_or_too_small | — | 0 | unchanged | none |
| tickmao/Rules | unsupported_or_too_small | — | 0 | unchanged | none |
| tickmao/Rules | unsupported_or_too_small | — | 0 | unchanged | none |
| bgpeer/rules | unsupported_or_too_small | — | 0 | unchanged | ambiguous |
| bgpeer/rules | unsupported_or_too_small | — | 0 | unchanged | ambiguous |
| bgpeer/rules | fetch_or_validation_error | — | 0 | unavailable | none |
| bgpeer/rules | unsupported_or_too_small | PROXY | 0 | unchanged | README_policy_reference |
| bgpeer/rules | unsupported_or_too_small | PROXY | 0 | unchanged | README_policy_reference |
| bgpeer/rules | unsupported_or_too_small | — | 0 | unchanged | ambiguous |
| bgpeer/rules | fetch_or_validation_error | — | 0 | unavailable | none |
| wcr1996/shadowrocket_rules | fetch_or_validation_error | — | 0 | unavailable | none |
| wcr1996/shadowrocket_rules | fetch_or_validation_error | — | 0 | unavailable | none |
| RzMY/IOS-AntiRevoke-DNS-Rules | shadowrocket-domain-rules | REJECT | 38 | unchanged | explicit_third_field |
| RzMY/IOS-AntiRevoke-DNS-Rules | unsupported_or_too_small | — | 0 | unchanged | none |
| RzMY/IOS-AntiRevoke-DNS-Rules | shadowrocket-domain-rules | REJECT | 38 | unchanged | explicit_third_field |

## Source update drift

- New source files: 0
- Changed source files: 1
- Added domain entries: 0
- Removed domain entries: 0
- Policy changes: 0

## Assessment details

### blackmatrix7/ios_rule_script

- URL: https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/China/China.list
- SHA-256: 65477cd1e2917a8ca09ba08132e9d9131c54c0d9e1cfcba0be2eaa8ea1a04b75
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 9; IP/CIDR/ASN 21
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### blackmatrix7/ios_rule_script

- URL: https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Global/Global.list
- SHA-256: cfbb192f30ba544b76206fd6046f98623242a9500d0d42ac152ec31a2975b5de
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 36; IP/CIDR/ASN 119
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### Loyalsoldier/v2ray-rules-dat

- URL: https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/direct-list.txt
- SHA-256: 7799323e9937cb93ab62a776cb22597d2206bfe5bf9ffbdad385809b2783e06f
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 109578; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### Loyalsoldier/v2ray-rules-dat

- URL: https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/proxy-list.txt
- SHA-256: f911b163c52407362f2ed6c8d504ecd32a338d20b07616dc8d398ffbc5483c09
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 26487; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### Loyalsoldier/v2ray-rules-dat

- URL: https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release/reject-list.txt
- SHA-256: unavailable
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### Hackl0us/SS-Rule-Snippet

- URL: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/CN.list
- SHA-256: 0d2395acec877713615e32f65b2922eae35e1cf4fd4bd2b742e2aaabdec35dfe
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 118; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 8; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### Hackl0us/SS-Rule-Snippet

- URL: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/foreign.list
- SHA-256: 0e9fa5ace2917751ea1c34bcf25feb1c8c44952b39078d211dfacd2624247be7
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 272; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 10; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### ACL4SSR/ACL4SSR

- URL: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ChinaDomain.list
- SHA-256: 362edd1f605742b360eaf138f151d7eea96cc17f20ef12da73acbfb80c350e08
- Exact DOMAIN: 23; DOMAIN-SUFFIX: 582; Adblock: 0; domain-only: 0; duplicate lines: 1
- Ignored non-domain rules: DOMAIN-KEYWORD 16; IP/CIDR/ASN 9
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: DIRECT

### ACL4SSR/ACL4SSR

- URL: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyGFWlist.list
- SHA-256: 72d5f97cb3adedd7ef632962effda4aa3b9953da20427cd6050d55d1184de5ea
- Exact DOMAIN: 7; DOMAIN-SUFFIX: 6759; Adblock: 0; domain-only: 0; duplicate lines: 101
- Ignored non-domain rules: DOMAIN-KEYWORD 26; IP/CIDR/ASN 84
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### ACL4SSR/ACL4SSR

- URL: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyLite.list
- SHA-256: 3792437f9641479c671ed57e4d3aa81505c5f7dc5d9087fdeabe76551ecda671
- Exact DOMAIN: 9; DOMAIN-SUFFIX: 297; Adblock: 0; domain-only: 0; duplicate lines: 7
- Ignored non-domain rules: DOMAIN-KEYWORD 26; IP/CIDR/ASN 84
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### sve1r/Rules-For-Quantumult-X

- URL: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/China.list
- SHA-256: 9fcc04d42430d2d73c34181c9ed1ad5192094692e7a1ed2b052ade8ee645ddfe
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 249; Adblock: 0; domain-only: 0; duplicate lines: 2
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {"DIRECT": 251}
- Policy evidence: ambiguous; candidate: none

### sve1r/Rules-For-Quantumult-X

- URL: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/Global.list
- SHA-256: 9dbd5581cb3b553036f09fc458ef7c91a6414b3968194ecf4c10f43c703471ec
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 574; Adblock: 0; domain-only: 0; duplicate lines: 234
- Ignored non-domain rules: DOMAIN-KEYWORD 17; IP/CIDR/ASN 0
- Explicit action counts: {"PROXY": 808}
- Policy evidence: explicit_third_field; candidate: PROXY

### sve1r/Rules-For-Quantumult-X

- URL: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Services/SNS/Weibo.list
- SHA-256: 5fcd1f04ad694a31e805ed8602f21a9851066a5e5bf7a8c117e1a7b8f1ea348b
- Exact DOMAIN: 1; DOMAIN-SUFFIX: 15; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 1; IP/CIDR/ASN 0
- Explicit action counts: {"REJECT": 3, "UNSUPPORTED": 13}
- Policy evidence: ambiguous; candidate: none

### gatework/surge-rules

- URL: https://raw.githubusercontent.com/gatework/surge-rules/release/direct.txt
- SHA-256: 0b9cc2038a64aa90431973660f33594a0b1e094f6c813a6ce18305e03b66b228
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 110088; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### gatework/surge-rules

- URL: https://raw.githubusercontent.com/gatework/surge-rules/release/gfw.txt
- SHA-256: b8323cbd838d959e82746528c88cf18c14d3b011a921269de9e4f3dbccf6cf51
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 4451; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### gatework/surge-rules

- URL: https://raw.githubusercontent.com/gatework/surge-rules/release/proxy.txt
- SHA-256: 670b9a2416a011bbdd9c23c909bdf6e8f43e56fa2b7071a4af7b9594065b3cbd
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 27254; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### Clash-FX/cn-apps-direct-domains

- URL: https://raw.githubusercontent.com/Clash-FX/cn-apps-direct-domains/main/apps-direct-domains.list
- SHA-256: 0a8a3a1bf8360495456da557bdbf22f5af8996dd7886dd82966a968491d8c27e
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 120; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {"DIRECT": 120}
- Policy evidence: explicit_third_field; candidate: DIRECT

### Jovanykoch/rules

- URL: https://raw.githubusercontent.com/Jovanykoch/rules/rel/gfw.list
- SHA-256: 15f4e63f0b66c9737633d07c975bb1b54a76009c44bb40888e82e4f4379e2943
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 4367; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### Jovanykoch/rules

- URL: https://raw.githubusercontent.com/Jovanykoch/rules/rel/loc-cn.list
- SHA-256: 2d756875ee2384e9d4050664dc23ac79a1d2af7a6b5ec0190d20ba1adb3834c5
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 6751; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: DIRECT

### Jovanykoch/rules

- URL: https://raw.githubusercontent.com/Jovanykoch/rules/rel/reject.list
- SHA-256: e26155f6869a6eb8e205116583a9264e08e35db176b36a3796e486523c44851e
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 957; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### GMOogway/shadowrocket-rules

- URL: https://raw.githubusercontent.com/GMOogway/shadowrocket-rules/master/docs/03.shadowsocks_tiny.conf
- SHA-256: a54d95cafe3f756ce2b0789c92a6fc1d228496ff62fba81b377b3b5cc5291b35
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/Loon.conf
- SHA-256: 151f55f8ae95a3a95e14079e01485395ec5dfa79648468709fed4380de49eb84
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/Shadowrocket.conf
- SHA-256: b7215e60ab7eb0015bf06868aec58361845bf62019a19493e0eefd5d241cecac
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: REJECT

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/chnroute-ipv4.txt
- SHA-256: e64ac99382db107ccf83af75230a3c6698cf2ec83336126e81329493681e3561
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: REJECT

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/chnroute-ipv6.txt
- SHA-256: cf0e7f0f72ceb30bda62e452d512d3591310a854b56eb366338f3a290a9d6090
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: REJECT

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/chnroute.txt
- SHA-256: ca67a60c6b72b1a4378271a07dd752b42dfcc6bad43dbf810a9d792660214a52
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: REJECT

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/ruleset/direct-special.list
- SHA-256: 8a37d52be15378a6fee3f7c4a98280278f466f3016a0829e80552898a2280e1b
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 1; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 2; IP/CIDR/ASN 31
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: DIRECT

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/ruleset/ipv6-cidr.list
- SHA-256: 429828bc6dd375c0276589640d37706217f64b2e9115cd615bb62c42b61c8cca
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 2018
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/ruleset/ipv6-cidr6.list
- SHA-256: ab20826ce00a3ec03f95048bf3f7154c788f69d9c7b886d0f7e5e780d94a61dc
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 2018
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/ruleset/proxy-special.list
- SHA-256: 3e4c721b23ed5a4da90771507447397ccecef6bc51055b76a7f79be6ff74fe90
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 14; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 4; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/ruleset/reject-special.list
- SHA-256: 72910d892e76f23858bd636b1e559132ba38358accea3302b94dddcfc38c5928
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 11; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 5; IP/CIDR/ASN 0
- Explicit action counts: {"UNSUPPORTED": 11}
- Policy evidence: README_policy_reference; candidate: REJECT

### PaPerseller/chn-iplist

- URL: https://raw.githubusercontent.com/PaPerseller/chn-iplist/master/v2rayA.txt
- SHA-256: 43bad67fdb5c22e689927df717b65096d7555c484ccf8149b68188858dc4ce99
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### Vann-Dev/proxy-list

- URL: https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/http.txt
- SHA-256: 4e7689feea22bacdef502c02d03a24b0ddde3ba3bd954120d5940126f5662e1b
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 1; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### Vann-Dev/proxy-list

- URL: https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/https.txt
- SHA-256: 04e1b35bd6174dbf17ec353f1a1c77194d5bccf67d702af455ab1ad5b483a22e
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 1; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### tickmao/Rules

- URL: https://raw.githubusercontent.com/tickmao/Rules/master/Loon/Loon.conf
- SHA-256: 6ff07e8b499ff29315a0902bb0c04270e1432457bf43ebac23e2faac0121c934
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### tickmao/Rules

- URL: https://raw.githubusercontent.com/tickmao/Rules/master/QuantumultX/QuantumultX.conf
- SHA-256: b3a1604dee6cdc9c2c5eaf2967d4df15b3f590d0d96c79a93157e56bf64b34e5
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### tickmao/Rules

- URL: https://raw.githubusercontent.com/tickmao/Rules/master/Shadowrocket/Shadowrocket.conf
- SHA-256: 8dda3cba70c21db5478db01adacfecee8e4ad7698ecb79ef12755e14812a0507
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### tickmao/Rules

- URL: https://raw.githubusercontent.com/tickmao/Rules/master/Surge/Surge.conf
- SHA-256: 45860b996eae7418f99ce85fdfc681d9d6f956a2fb93a4080169d212d445b5a5
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### bgpeer/rules

- URL: https://raw.githubusercontent.com/bgpeer/rules/main/QX.conf
- SHA-256: c37f189406dd6505d989d1fa64de24bdaa421095a8a0ee1e9ed507bf640845f7
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 5
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### bgpeer/rules

- URL: https://raw.githubusercontent.com/bgpeer/rules/main/QX/geoip/cn.list
- SHA-256: cee39710615dc597b8e74320ae7e24e6bde290a21870e860aaa5548f57c048ca
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 9673
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### bgpeer/rules

- URL: https://raw.githubusercontent.com/bgpeer/rules/main/QX/geosite/cn.list
- SHA-256: unavailable
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### bgpeer/rules

- URL: https://raw.githubusercontent.com/bgpeer/rules/main/Shadowrocket.conf
- SHA-256: 7500ca318930461c0eb64a37dbb5fa62fb4830f5842fe2e91b824524ad7abdad
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### bgpeer/rules

- URL: https://raw.githubusercontent.com/bgpeer/rules/main/Surge.conf
- SHA-256: 1347b5c2e2edd792efea6a2ec288c602bc591211a78edbd076360a696b2c9a9c
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: README_policy_reference; candidate: PROXY

### bgpeer/rules

- URL: https://raw.githubusercontent.com/bgpeer/rules/main/geo/geoip/cn.list
- SHA-256: 5a7d204c541039c9d246cf40f4323c0e0ff58026b90f7075d176d80bc3493c6d
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 15080
- Explicit action counts: {}
- Policy evidence: ambiguous; candidate: none

### bgpeer/rules

- URL: https://raw.githubusercontent.com/bgpeer/rules/main/geo/geosite/cn.list
- SHA-256: unavailable
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### wcr1996/shadowrocket_rules

- URL: https://raw.githubusercontent.com/wcr1996/shadowrocket_rules/main/blacklist.conf
- SHA-256: unavailable
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### wcr1996/shadowrocket_rules

- URL: https://raw.githubusercontent.com/wcr1996/shadowrocket_rules/main/whitelist.conf
- SHA-256: unavailable
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### RzMY/IOS-AntiRevoke-DNS-Rules

- URL: https://raw.githubusercontent.com/RzMY/IOS-AntiRevoke-DNS-Rules/main/output/RevokeGuard_Loon.txt
- SHA-256: 5519a4db7a572d97b600562a50e930b99e8568ae1ffa387d6862245dfed5c195
- Exact DOMAIN: 38; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {"REJECT": 38}
- Policy evidence: explicit_third_field; candidate: REJECT

### RzMY/IOS-AntiRevoke-DNS-Rules

- URL: https://raw.githubusercontent.com/RzMY/IOS-AntiRevoke-DNS-Rules/main/output/RevokeGuard_QuantumultX.txt
- SHA-256: 3fb6445beac9fa2a104ca416b350e320aa4da02c2155f7a3a1ae607b036a8825
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

### RzMY/IOS-AntiRevoke-DNS-Rules

- URL: https://raw.githubusercontent.com/RzMY/IOS-AntiRevoke-DNS-Rules/main/output/RevokeGuard_Shadowrocket.txt
- SHA-256: 5519a4db7a572d97b600562a50e930b99e8568ae1ffa387d6862245dfed5c195
- Exact DOMAIN: 38; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 0; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {"REJECT": 38}
- Policy evidence: explicit_third_field; candidate: REJECT

## Activation gate

A parser candidate is not a trusted source. Activation still requires declared policy semantics, independent publishers, lineage checks, parser tests, stable update history, and all per-policy confidence gates. This report is advisory and cannot alter sources/domain_sources.json.
