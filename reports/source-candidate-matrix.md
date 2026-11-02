# Automated source candidate matrix

This report combines parser compatibility, explicit policy evidence and README reference overlap. It does not activate sources.

| Policy | Candidate publishers | Eligible publishers | Candidate files | Ready |
|---|---:|---:|---:|---|
| DIRECT | 5 | 4 | 7 | yes |
| PROXY | 6 | 5 | 11 | yes |
| REJECT | 7 | 4 | 90 | yes |

## Same-policy source overlap

- DIRECT: Jovanykoch/rules ↔ ACL4SSR/ACL4SSR — 439 shared domains; 72.6% of smaller set; high_overlap
- DIRECT: Jovanykoch/rules ↔ h2y/Shadowrocket-ADBlock-Rules — 42 shared domains; 12.9% of smaller set; partial_overlap
- DIRECT: Jovanykoch/rules ↔ Hackl0us/SS-Rule-Snippet — 93 shared domains; 66.9% of smaller set; partial_overlap
- DIRECT: Jovanykoch/rules ↔ Clash-FX/cn-apps-direct-domains — 83 shared domains; 69.2% of smaller set; partial_overlap
- DIRECT: ACL4SSR/ACL4SSR ↔ h2y/Shadowrocket-ADBlock-Rules — 35 shared domains; 10.8% of smaller set; partial_overlap
- DIRECT: ACL4SSR/ACL4SSR ↔ Hackl0us/SS-Rule-Snippet — 101 shared domains; 72.7% of smaller set; high_overlap
- DIRECT: ACL4SSR/ACL4SSR ↔ Clash-FX/cn-apps-direct-domains — 73 shared domains; 60.8% of smaller set; partial_overlap
- DIRECT: h2y/Shadowrocket-ADBlock-Rules ↔ Hackl0us/SS-Rule-Snippet — 22 shared domains; 15.8% of smaller set; partial_overlap
- DIRECT: h2y/Shadowrocket-ADBlock-Rules ↔ Clash-FX/cn-apps-direct-domains — 13 shared domains; 10.8% of smaller set; partial_overlap
- DIRECT: Hackl0us/SS-Rule-Snippet ↔ Clash-FX/cn-apps-direct-domains — 29 shared domains; 24.2% of smaller set; partial_overlap
- PROXY: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ ACL4SSR/ACL4SSR — 4621 shared domains; 67.8% of smaller set; partial_overlap
- PROXY: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ h2y/Shadowrocket-ADBlock-Rules — 3619 shared domains; 64.9% of smaller set; partial_overlap
- PROXY: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ gatework/surge-rules — 4419 shared domains; 99.3% of smaller set; near_duplicate
- PROXY: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ sve1r/Rules-For-Quantumult-X — 300 shared domains; 37.0% of smaller set; partial_overlap
- PROXY: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ Hackl0us/SS-Rule-Snippet — 278 shared domains; 56.4% of smaller set; partial_overlap
- PROXY: ACL4SSR/ACL4SSR ↔ h2y/Shadowrocket-ADBlock-Rules — 5040 shared domains; 90.4% of smaller set; high_overlap
- PROXY: ACL4SSR/ACL4SSR ↔ gatework/surge-rules — 3786 shared domains; 85.1% of smaller set; high_overlap
- PROXY: ACL4SSR/ACL4SSR ↔ sve1r/Rules-For-Quantumult-X — 371 shared domains; 45.7% of smaller set; partial_overlap
- PROXY: ACL4SSR/ACL4SSR ↔ Hackl0us/SS-Rule-Snippet — 339 shared domains; 68.8% of smaller set; partial_overlap
- PROXY: h2y/Shadowrocket-ADBlock-Rules ↔ gatework/surge-rules — 2816 shared domains; 63.3% of smaller set; partial_overlap
- PROXY: h2y/Shadowrocket-ADBlock-Rules ↔ sve1r/Rules-For-Quantumult-X — 286 shared domains; 35.2% of smaller set; partial_overlap
- PROXY: h2y/Shadowrocket-ADBlock-Rules ↔ Hackl0us/SS-Rule-Snippet — 270 shared domains; 54.8% of smaller set; partial_overlap
- PROXY: gatework/surge-rules ↔ sve1r/Rules-For-Quantumult-X — 248 shared domains; 30.5% of smaller set; partial_overlap
- PROXY: gatework/surge-rules ↔ Hackl0us/SS-Rule-Snippet — 226 shared domains; 45.8% of smaller set; partial_overlap
- PROXY: sve1r/Rules-For-Quantumult-X ↔ Hackl0us/SS-Rule-Snippet — 453 shared domains; 91.9% of smaller set; high_overlap
- REJECT: hagezi/dns-blocklists ↔ Johnshall/Shadowrocket-ADBlock-Rules-Forever — 50601 shared domains; 97.2% of smaller set; near_duplicate
- REJECT: hagezi/dns-blocklists ↔ sve1r/Rules-For-Quantumult-X — 39211 shared domains; 36.8% of smaller set; partial_overlap
- REJECT: hagezi/dns-blocklists ↔ h2y/Shadowrocket-ADBlock-Rules — 2653 shared domains; 16.4% of smaller set; partial_overlap
- REJECT: hagezi/dns-blocklists ↔ TG-Twilight/AWAvenue-Ads-Rule — 733 shared domains; 75.6% of smaller set; high_overlap
- REJECT: hagezi/dns-blocklists ↔ Hackl0us/SS-Rule-Snippet — 239 shared domains; 41.2% of smaller set; partial_overlap
- REJECT: hagezi/dns-blocklists ↔ anudeepND/whitelist — 51 shared domains; 19.1% of smaller set; partial_overlap
- REJECT: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ sve1r/Rules-For-Quantumult-X — 21928 shared domains; 42.1% of smaller set; partial_overlap
- REJECT: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ h2y/Shadowrocket-ADBlock-Rules — 2250 shared domains; 14.0% of smaller set; partial_overlap
- REJECT: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ TG-Twilight/AWAvenue-Ads-Rule — 64 shared domains; 6.6% of smaller set; partial_overlap
- REJECT: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ Hackl0us/SS-Rule-Snippet — 183 shared domains; 31.6% of smaller set; partial_overlap
- REJECT: Johnshall/Shadowrocket-ADBlock-Rules-Forever ↔ anudeepND/whitelist — 21 shared domains; 7.9% of smaller set; partial_overlap
- REJECT: sve1r/Rules-For-Quantumult-X ↔ h2y/Shadowrocket-ADBlock-Rules — 3575 shared domains; 22.2% of smaller set; partial_overlap
- REJECT: sve1r/Rules-For-Quantumult-X ↔ TG-Twilight/AWAvenue-Ads-Rule — 705 shared domains; 72.8% of smaller set; high_overlap
- REJECT: sve1r/Rules-For-Quantumult-X ↔ Hackl0us/SS-Rule-Snippet — 511 shared domains; 88.1% of smaller set; high_overlap
- REJECT: sve1r/Rules-For-Quantumult-X ↔ anudeepND/whitelist — 35 shared domains; 13.1% of smaller set; partial_overlap
- REJECT: h2y/Shadowrocket-ADBlock-Rules ↔ TG-Twilight/AWAvenue-Ads-Rule — 27 shared domains; 2.8% of smaller set; partial_overlap
- REJECT: h2y/Shadowrocket-ADBlock-Rules ↔ Hackl0us/SS-Rule-Snippet — 137 shared domains; 23.6% of smaller set; partial_overlap
- REJECT: h2y/Shadowrocket-ADBlock-Rules ↔ anudeepND/whitelist — 3 shared domains; 1.1% of smaller set; partial_overlap
- REJECT: TG-Twilight/AWAvenue-Ads-Rule ↔ Hackl0us/SS-Rule-Snippet — 27 shared domains; 4.7% of smaller set; partial_overlap
- REJECT: TG-Twilight/AWAvenue-Ads-Rule ↔ anudeepND/whitelist — 1 shared domains; 0.4% of smaller set; partial_overlap
- REJECT: Hackl0us/SS-Rule-Snippet ↔ anudeepND/whitelist — 1 shared domains; 0.4% of smaller set; partial_overlap

## Cross-policy overlap

- DIRECT / PROXY: 389 shared domain fingerprints; held for conflict review.
- DIRECT / REJECT: 408 shared domain fingerprints; held for conflict review.
- PROXY / REJECT: 1982 shared domain fingerprints; held for conflict review.

## Candidate publishers

### DIRECT — Jovanykoch/rules

- Domain entries across candidate files: 6771
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: 0xDarkMatter/aegis-blocklist, 27Aaron/ProxyRules, ChopsGarbageCollection/chops-mobile-blocklist, CorleoneSalute/SHADOW-BLOCKER-BLOCKLIST, DDcat2025/douyin-bytedance-shadowrocket-rules, DDcat2025/openai-shadowrocket-rules, DDcat2025/shadowrocket-routing-rules, DDcat2025/tencent-shadowrocket-rules, DXC-0/respect-my-internet, EastonSun/ProxyRules, FadeMind/hosts.whitelists, Flo5k5/proxyware-blocklist, GMOogway/shadowrocket-rules, GrandpaNiuu/cn-direct-rules, Infinitty35/shadowrocket-adblock, Jeliren/shadowrocket-russia-direct, Jo-CRuiSe/siri-ai-rules, Kimberlysz/shadowrocket-rules, Knight4LHB/shadowrocket-rules, Loyalsoldier/v2ray-rules-dat, Magisk-Modules-Alt-Repo/StevenBlock, MikhailKasimov/validin-phish-feed, MuMu2223/SSShadowrocket-Rules, OriginVorfeed/shadowrocket-china-list, PaPerseller/chn-iplist, Remix123/routingrulehub, SeanCode-super/shadowrocket-routing-rules, Seanyim/tailrocket, VPSDance/ai-proxy-rules, Xiaobei09/Rule-Provider, actusnileh/geoip-geosite-list, amzonmeeee/Shadowrocket_Rules, beikejinmiao/titrace, bgpeer/rules, busymilk/v2fly-domain-list-community_rule_set, crayonluffy/shadowrocket-rules, denis-g/rpi4-pihole-settings, dgomesbr/fightback-consumer-tv, dmulle12/rules, ez4y2f/SurgeRulesAutoBuild, fernvenue/chn-domains-list, gatework/surge-rules, hl2guide/AdGuard-Home-AIO-List, iill392/youlong-BlockAds, jarelllama/Scam-Blocklist, jhz1022/Shadowrocket-Rules, julxxy/smart-proxy-rules, kaonimei/Shadowrocket-ADBlock-Rules, mahlenko/shadowrocket-rules-v2fly, marco-acorte/antispam-it, mikropsoft/StevenBlock, moesnow/Shadowrocket-Rules, mofanxt/shadowrocket-rules, momenbasel/puresnitch, moshall/egloon_rule_hub, niansi1/Shadowrocket-Rules, nihestver/ru-geo-lists, passionsu-su/china-direct-domain, poohyeban/shadowrocket-rules, privacyfilters/Microsoft-Blocker, privacyfilters/Mozilla-Blocker, proxyBug/tigertrade-moomoo-rules, ruijzhan/chnroute, tkgeeked/clash-rules-for-shadowrocket, vannt-dev/aegis-net, zachlagden/Pi-hole-Optimized-Blocklists, zangadoprojets/pi-hole-blocklist
- Activation eligible: True
- Blockers: none

  - domain-only: https://raw.githubusercontent.com/Jovanykoch/rules/rel/loc-cn.list (6771 domain entries)

### DIRECT — ACL4SSR/ACL4SSR

- Domain entries across candidate files: 605
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ChinaDomain.list (605 domain entries)

### DIRECT — h2y/Shadowrocket-ADBlock-Rules

- Domain entries across candidate files: 325
- Policy evidence: source_header_claim
- Lineage: unverified (readme_unavailable)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: policy_evidence_not_strong, publisher_archived

  - domain-only: https://raw.githubusercontent.com/h2y/Shadowrocket-ADBlock-Rules/master/factory/resultant/top500_direct.list (325 domain entries)

### DIRECT — Hackl0us/SS-Rule-Snippet

- Domain entries across candidate files: 257
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: JohnyP36/Personal-List, VenexGit/DeepGuard, badmojr/1Hosts, busymilk/v2fly-domain-list-community_rule_set, easylist/easylist, helmiau/clashrules, omerdduran/turk-adfilter, privacyfilters/Microsoft-Blocker, proxyBug/zoom-rules
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/%E8%A7%84%E5%88%99%E7%89%87%E6%AE%B5%E9%9B%86/%E5%9F%BA%E7%A1%80%E8%A7%84%E5%88%99%E9%9B%86/%E5%9B%BD%E5%86%85%E7%9B%B4%E8%BF%9E.txt (119 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/%E8%A7%84%E5%88%99%E7%89%87%E6%AE%B5%E9%9B%86/%E8%87%AA%E9%80%89%E8%A7%84%E5%88%99%E9%9B%86/%E5%AD%A6%E6%9C%AF%E7%BD%91%E7%AB%99-%E7%9B%B4%E8%BF%9E.txt (20 domain entries)
  - quantumult-domain-rules: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Quantumult/Basic/CN.list (118 domain entries)

### DIRECT — Clash-FX/cn-apps-direct-domains

- Domain entries across candidate files: 120
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Clash-FX/cn-apps-direct-domains/main/apps-direct-domains.list (120 domain entries)

### PROXY — Johnshall/Shadowrocket-ADBlock-Rules-Forever

- Domain entries across candidate files: 30554
- Policy evidence: explicit_third_field
- Lineage: unverified (readme_unavailable)
- Possible shared README-reference peers: none found
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_cnip.conf (371 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_top500_banlist.conf (30183 domain entries)

### PROXY — ACL4SSR/ACL4SSR

- Domain entries across candidate files: 7072
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyGFWlist.list (6766 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyLite.list (306 domain entries)

### PROXY — h2y/Shadowrocket-ADBlock-Rules

- Domain entries across candidate files: 5645
- Policy evidence: explicit_third_field, source_header_claim
- Lineage: unverified (readme_unavailable)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: publisher_archived

  - domain-only: https://raw.githubusercontent.com/h2y/Shadowrocket-ADBlock-Rules/master/factory/resultant/top500_proxy.list (99 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/h2y/Shadowrocket-ADBlock-Rules/master/sr_top500_banlist.conf (5546 domain entries)

### PROXY — gatework/surge-rules

- Domain entries across candidate files: 4451
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: 27Aaron/ProxyRules, CorleoneSalute/SHADOW-BLOCKER-BLOCKLIST, DDcat2025/douyin-bytedance-shadowrocket-rules, DDcat2025/openai-shadowrocket-rules, DDcat2025/shadowrocket-routing-rules, DDcat2025/tencent-shadowrocket-rules, EastonSun/ProxyRules, GMOogway/shadowrocket-rules, GrandpaNiuu/cn-direct-rules, Jeliren/shadowrocket-russia-direct, Jo-CRuiSe/siri-ai-rules, Jovanykoch/rules, Kimberlysz/shadowrocket-rules, Knight4LHB/shadowrocket-rules, Loyalsoldier/v2ray-rules-dat, OriginVorfeed/shadowrocket-china-list, PaPerseller/chn-iplist, Remix123/routingrulehub, SeanCode-super/shadowrocket-routing-rules, VPSDance/ai-proxy-rules, Xiaobei09/Rule-Provider, actusnileh/geoip-geosite-list, amzonmeeee/Shadowrocket_Rules, bacdown/rules, bgpeer/rules, busymilk/v2fly-domain-list-community_rule_set, crayonluffy/shadowrocket-rules, daveytang/ruleset, dmulle12/rules, ez4y2f/SurgeRulesAutoBuild, fernvenue/chn-domains-list, jfox52/ruleset, jhz1022/Shadowrocket-Rules, kaonimei/Shadowrocket-ADBlock-Rules, mahlenko/shadowrocket-rules-v2fly, moesnow/Shadowrocket-Rules, mofanxt/shadowrocket-rules, moshall/egloon_rule_hub, niansi1/Shadowrocket-Rules, nihestver/ru-geo-lists, passionsu-su/china-direct-domain, poohyeban/shadowrocket-rules, proxyBug/tigertrade-moomoo-rules, tkgeeked/clash-rules-for-shadowrocket
- Activation eligible: True
- Blockers: none

  - domain-only: https://raw.githubusercontent.com/gatework/surge-rules/release/gfw.txt (4451 domain entries)

### PROXY — sve1r/Rules-For-Quantumult-X

- Domain entries across candidate files: 814
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: EastonSun/ProxyRules, Infinitty35/shadowrocket-adblock, iill392/youlong-BlockAds, jackwoo725-ux/shadowrocket-rules, julxxy/smart-proxy-rules, pikipig/surge-5-anti-ad
- Activation eligible: True
- Blockers: none

  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/BackCN/BackCN.list (240 domain entries)
  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/Global.list (574 domain entries)

### PROXY — Hackl0us/SS-Rule-Snippet

- Domain entries across candidate files: 526
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: JohnyP36/Personal-List, VenexGit/DeepGuard, badmojr/1Hosts, busymilk/v2fly-domain-list-community_rule_set, easylist/easylist, helmiau/clashrules, omerdduran/turk-adfilter, privacyfilters/Microsoft-Blocker, proxyBug/zoom-rules
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/%E8%A7%84%E5%88%99%E7%89%87%E6%AE%B5%E9%9B%86/%E8%87%AA%E9%80%89%E8%A7%84%E5%88%99%E9%9B%86/%E5%B8%B8%E8%A7%81%E5%9B%BD%E5%A4%96%E7%BD%91%E7%AB%99%E5%88%97%E8%A1%A8.txt (254 domain entries)
  - quantumult-domain-rules: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Quantumult/Basic/foreign.list (272 domain entries)

### REJECT — hagezi/dns-blocklists

- Domain entries across candidate files: 2964336
- Policy evidence: source_header_claim
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: ChopsGarbageCollection/chops-mobile-blocklist, privacyfilters/Microsoft-Blocker, privacyfilters/Mozilla-Blocker, sikysikov/adguard-wildcard-blocklist, term7/Break-Apple-Blocklist
- Activation eligible: False
- Blockers: policy_evidence_not_strong

  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/anti.piracy.txt (58450 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/blocklist-referral-native.txt (1695 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/doh-vpn-proxy-bypass.txt (16556 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/doh.top.txt (301 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/doh.txt (3597 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/dyndns.txt (1534 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/fake.txt (17515 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/gambling.medium.txt (180817 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/gambling.mini.txt (112689 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/hoster.txt (1074 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/light.txt (79665 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/multi.txt (176107 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.amazon.txt (369 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.apple.txt (110 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.huawei.txt (135 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.lgwebos.txt (231 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.oppo-realme.txt (490 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.roku.txt (57 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.samsung.txt (201 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.tiktok.extended.txt (764 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.tiktok.txt (550 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.vivo.txt (247 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.winoffice.txt (384 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/native.xiaomi.txt (350 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/nosafesearch.txt (201 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/popupads.txt (77621 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.mini.txt (93657 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.plus.mini.txt (105218 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/pro.txt (211778 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/social.txt (8166 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/tif.mini.txt (191527 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/ultimate.mini.txt (129560 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/adblock/urlshortener.txt (9855 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/anti.piracy-onlydomains.txt (58450 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/blocklist-referral-onlydomains.txt (1695 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/doh-onlydomains.txt (3597 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/doh-vpn-proxy-bypass-onlydomains.txt (16556 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/dyndns-onlydomains.txt (1534 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/fake-onlydomains.txt (17515 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/gambling.medium-onlydomains.txt (180817 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/gambling.mini-onlydomains.txt (112689 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/hoster-onlydomains.txt (1074 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/light-onlydomains.txt (79665 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/multi-onlydomains.txt (176107 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.amazon-onlydomains.txt (369 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.apple-onlydomains.txt (110 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.huawei-onlydomains.txt (135 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.lgwebos-onlydomains.txt (231 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.oppo-realme-onlydomains.txt (490 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.roku-onlydomains.txt (57 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.samsung-onlydomains.txt (201 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.tiktok-onlydomains.txt (550 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.tiktok.extended-onlydomains.txt (764 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.vivo-onlydomains.txt (247 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.winoffice-onlydomains.txt (384 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/native.xiaomi-onlydomains.txt (350 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/nosafesearch-onlydomains.txt (201 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/popupads-onlydomains.txt (77621 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro-onlydomains.txt (211778 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro.mini-onlydomains.txt (93657 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/pro.plus.mini-onlydomains.txt (105218 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/social-onlydomains.txt (8166 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/tif.mini-onlydomains.txt (191527 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/ultimate.mini-onlydomains.txt (129560 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/urlshortener-onlydomains.txt (9855 domain entries)
  - domain-only: https://raw.githubusercontent.com/hagezi/dns-blocklists/main/wildcard/whitelist-referral-onlydomains.txt (1695 domain entries)

### REJECT — Johnshall/Shadowrocket-ADBlock-Rules-Forever

- Domain entries across candidate files: 208240
- Policy evidence: explicit_third_field
- Lineage: unverified (readme_unavailable)
- Possible shared README-reference peers: none found
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_ad_only.conf (52060 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_backcn_ad.conf (52060 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_direct_banad.conf (52060 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Johnshall/Shadowrocket-ADBlock-Rules-Forever/release/sr_proxy_banad.conf (52060 domain entries)

### REJECT — sve1r/Rules-For-Quantumult-X

- Domain entries across candidate files: 119067
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: EastonSun/ProxyRules, Infinitty35/shadowrocket-adblock, iill392/youlong-BlockAds, jackwoo725-ux/shadowrocket-rules, julxxy/smart-proxy-rules, pikipig/surge-5-anti-ad
- Activation eligible: True
- Blockers: none

  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Advertising/AdReject.list (8179 domain entries)
  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Advertising/AdRule.list (7963 domain entries)
  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Advertising/Hijacking.list (178 domain entries)
  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Advertising/antiAD-V4.list (102721 domain entries)
  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/App/TomatoNovel.list (26 domain entries)

### REJECT — h2y/Shadowrocket-ADBlock-Rules

- Domain entries across candidate files: 48375
- Policy evidence: explicit_third_field
- Lineage: unverified (readme_unavailable)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: publisher_archived

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/h2y/Shadowrocket-ADBlock-Rules/master/sr_backcn_ad.conf (16125 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/h2y/Shadowrocket-ADBlock-Rules/master/sr_direct_banad.conf (16125 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/h2y/Shadowrocket-ADBlock-Rules/master/sr_proxy_banad.conf (16125 domain entries)

### REJECT — TG-Twilight/AWAvenue-Ads-Rule

- Domain entries across candidate files: 6520
- Policy evidence: README_policy_reference, explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: BlackRabbitZ/BlackRabbitZ-DNS-Blocklists, ZingyAwesome/easylists-for-pihole, hl2guide/Filterlist-for-AdGuard-or-PiHole, privacyfilters/Microsoft-Blocker, privacyfilters/Mozilla-Blocker
- Activation eligible: True
- Blockers: none

  - adblock-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/AWAvenue-Ads-Rule.txt (969 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-Adguard-No.Privacy.txt (755 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-Adguard-No.Unwelcome.txt (872 domain entries)
  - adblock-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-Adguard-Only.Ads.txt (658 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-QuantumultX-No.Privacy.list (758 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-QuantumultX-No.Unwelcome.list (875 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-QuantumultX-Only.Ads.list (661 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/TG-Twilight/AWAvenue-Ads-Rule/main/Filters/AWAvenue-Ads-Rule-QuantumultX.list (972 domain entries)

### REJECT — Hackl0us/SS-Rule-Snippet

- Domain entries across candidate files: 580
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: JohnyP36/Personal-List, VenexGit/DeepGuard, badmojr/1Hosts, busymilk/v2fly-domain-list-community_rule_set, easylist/easylist, helmiau/clashrules, omerdduran/turk-adfilter, privacyfilters/Microsoft-Blocker, proxyBug/zoom-rules
- Activation eligible: True
- Blockers: none

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/%E8%A7%84%E5%88%99%E7%89%87%E6%AE%B5%E9%9B%86/%E8%87%AA%E9%80%89%E8%A7%84%E5%88%99%E9%9B%86/%E5%B1%8F%E8%94%BD%E8%A7%86%E9%A2%91%E5%B9%BF%E5%91%8A.txt (157 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/%E8%A7%84%E5%88%99%E7%89%87%E6%AE%B5%E9%9B%86/%E8%87%AA%E9%80%89%E8%A7%84%E5%88%99%E9%9B%86/%E5%B9%BF%E5%91%8A%E5%9F%9F%E5%90%8D%E5%88%97%E8%A1%A8.txt (423 domain entries)

### REJECT — anudeepND/whitelist

- Domain entries across candidate files: 267
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: publisher_archived

  - domain-only: https://raw.githubusercontent.com/anudeepND/whitelist/master/domains/referral-sites.txt (76 domain entries)
  - domain-only: https://raw.githubusercontent.com/anudeepND/whitelist/master/domains/whitelist.txt (191 domain entries)

## Safety rule

Publisher count is repository-level, not file-level: several files from one repository count as one publisher. Domain overlap uses salted-free truncated SHA-256 fingerprints, not raw domain names. Near-identical source sets are grouped as one possible publisher lineage; high overlap is a correlation warning, not proof of common ancestry. README hyperlinks are only possible shared-reference signals. Lineage gaps and shared README references are provenance/correlation warnings, not vetoes. Strong policy evidence, non-archived publishers, independent-publisher checks and domain-level safety gates remain mandatory. This matrix does not auto-edit the active source registry.
