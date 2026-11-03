# Shadowrocket user-config baseline audit

- Mode: read-only; user-managed config is authoritative
- Baseline file: `shadowrocket/ss.conf`
- Baseline Git blob SHA: `b87f4c3bf13ed76d7f01ecc77266793da0e7556b`
- Registered baseline SHA matches: **True**
- Sections: **5**
- Rule lines: **1943**
- URL Rewrite lines: **10**
- MITM section present: **True**
- MITM enabled: **False**
- DNS invariants match policy: **True**

## DNS snapshot (observed; not changed)

- `dns-server`: `https://dns.quad9.net/dns-query#proxy&no-h3, https://dns.google/dns-query#proxy&no-h3`
- `fallback-dns-server`: `https://cloudflare-dns.com/dns-query#no-h3`
- `direct-dns-server`: `https://doh.pub/dns-query#no-h3, https://dns.alidns.com/dns-query#no-h3`
- `proxy-dns-server`: `https://dns.quad9.net/dns-query#no-h3, https://dns.google/dns-query#no-h3`
- `dns-direct-system`: `false`
- `dns-direct-fallback-proxy`: `false`
- `hijack-dns`: `:53`

## Interpretation

All checks use the current user-managed `shadowrocket/ss.conf` as the sole authority.
A registered-hash mismatch means the config changed without its baseline record being updated; it does not authorize the automation to rewrite the config.
DNS and MITM are reported only. No settings are added, removed, or changed.
