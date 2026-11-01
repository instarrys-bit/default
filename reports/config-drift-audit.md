# Shadowrocket configuration drift audit

- Mode: read-only
- Managed config SHA-256: `165680967a319b9e8df630ba6fa4181c545c56aca94b7432cd8031080e5b2224`
- Canonical baseline SHA-256: `f2a2a91d4853ea83fb55d406659c1cde4f3d29092a9e08d4a3a80e00015446c8`
- Differences from baseline: **23**
- DNS-related differences: **4**
- MITM section present: **True**
- MITM enabled: **True**

## Detected differences

| Section | Key | Change | Baseline | Managed |
|---|---|---|---|---|
| General | block-quic | added_key | null | ["all-proxy"] |
| General | bypass-system | removed_key | ["true"] | null |
| General | compatibility-mode | added_key | null | ["3"] |
| General | direct-dns-server | changed_value | ["https://doh.pub/dns-query#no-h3, https://dns.alidns.com/dns-query#no-h3, https://sm2.doh.pub/dns-query#no-h3, https://doh.360.cn/dns-query#no-h3"] | ["https://doh.pub/dns-query#no-h3, https://dns.alidns.com/dns-query#no-h3, https://sm2.doh.pub/dns-query#no-h3"] |
| General | dns-server | changed_value | ["https://dns.quad9.net/dns-query#proxy&no-h3, https://cloudflare-dns.com/dns-query#proxy&no-h3, https://dns.google/dns-query#proxy&no-h3"] | ["https://dns.google/dns-query#proxy&ecs=114.114.114.0/24|2400:3200::/32&ecs-override=true&no-h3, https://dns.quad9.net/dns-query#proxy&no-h3, https://cloudflare-dns.com/dns-query#proxy&no-h3"] |
| General | fallback-dns-server | changed_value | ["https://cloudflare-dns.com/dns-query#proxy&no-h3, https://dns.google/dns-query#proxy&no-h3, https://dns.quad9.net/dns-query#proxy&no-h3"] | ["https://doh.pub/dns-query#no-h3, https://dns.alidns.com/dns-query#no-h3"] |
| General | proxy-dns-server | changed_value | ["https://doh.pub/dns-query#no-h3, https://dns.alidns.com/dns-query#no-h3, https://sm2.doh.pub/dns-query#no-h3, https://doh.360.cn/dns-query#no-h3"] | ["https://dns.quad9.net/dns-query#proxy&no-h3, https://dns.google/dns-query#proxy&no-h3, https://cloudflare-dns.com/dns-query#proxy&no-h3"] |
| Host | 8888.google | removed_key | ["8.8.8.8"] | null |
| Host | cloudflare-dns.com | removed_key | ["1.1.1.1"] | null |
| Host | dns.google | removed_key | ["8.8.8.8"] | null |
| Host | dns.google.com | removed_key | ["8.8.8.8"] | null |
| Host | dns.quad9.net | removed_key | ["9.9.9.9"] | null |
| Host | dns10.quad9.net | removed_key | ["149.112.112.112"] | null |
| Host | dns11.quad9.net | removed_key | ["9.9.9.11"] | null |
| Host | dns64.dns.google | removed_key | ["8.8.8.8"] | null |
| Host | dns9.quad9.net | removed_key | ["9.9.9.9"] | null |
| Host | doh.360.cn | removed_key | ["101.226.4.6"] | null |
| Host | one.one.one.one | removed_key | ["1.1.1.1"] | null |
| MITM | * | added_section | null | null |
| Rule | url-regex,^http:\/\/([0-9.]+|\[[0-9a-fa-f:]+\])\/d(\?dn | removed_key | ["|$),REJECT"] | null |
| Rule | url-regex,^http:\/\/([0-9.]+|\[[0-9a-fa-f:]+\])\/fetch\?dm | removed_key | [",REJECT"] | null |
| Rule | url-regex,^http:\/\/[^\/]+\/multifetch\?dms | removed_key | [",REJECT"] | null |
| URL Rewrite | ^http:\/\/([0-9.]+|\[[0-9a-fa-f:]+\])\/d(\?dn | removed_key | ["|$) _ reject"] | null |

## Interpretation

This is an automatic, read-only drift report. It does not edit the user's config or rewrite DNS/MITM settings.
A difference is flagged for inspection; the automation does not assume the canonical baseline is the desired current runtime config.
