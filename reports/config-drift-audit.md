# Shadowrocket user-config baseline audit

- Mode: read-only; user-managed config is authoritative
- Baseline file: `shadowrocket/ss.conf`
- Baseline Git blob SHA: `6fd417b8d6c41f1e112014828e4849adc9be280c`
- Registered baseline SHA matches: **True**
- Sections: **5**
- Rule lines: **2271**
- URL Rewrite lines: **10**
- MITM section present: **True**
- MITM enabled: **True**

## DNS snapshot (observed; not changed)

- `dns-server`: `https://dns.google/dns-query#proxy&ecs=114.114.114.0/24|2400:3200::/32&ecs-override=true&no-h3, https://dns.quad9.net/dns-query#proxy&no-h3, https://cloudflare-dns.com/dns-query#proxy&no-h3`
- `fallback-dns-server`: `https://doh.pub/dns-query#no-h3, https://dns.alidns.com/dns-query#no-h3`
- `direct-dns-server`: `https://doh.pub/dns-query#no-h3, https://dns.alidns.com/dns-query#no-h3, https://sm2.doh.pub/dns-query#no-h3`
- `proxy-dns-server`: `https://dns.quad9.net/dns-query#proxy&no-h3, https://dns.google/dns-query#proxy&no-h3, https://cloudflare-dns.com/dns-query#proxy&no-h3`
- `dns-direct-system`: `false`
- `dns-direct-fallback-proxy`: `false`
- `hijack-dns`: `:53`

## Interpretation

All checks use the current user-managed config as the authority. The historical uploaded baseline is not used to judge whether this config is correct.
A registered-hash mismatch means the config changed without its baseline record being updated; it does not authorize the automation to rewrite the config.
DNS and MITM are reported only. No settings are added, removed, or changed.
