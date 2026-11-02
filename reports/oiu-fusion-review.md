# oiu.conf Fusion Review

## Scope
- Base: current `shadowrocket/ss.conf`
- Base blob SHA: `a6b2f0e6e41da13572dfca8e8119212118df5bcb`
- Uploaded reference: `oiu.conf`
- This is an independent candidate only. The production `shadowrocket/ss.conf` was not changed.

## Accepted into candidate
1. Added the AliDNS host bootstrap mapping under `[Host]`:
   `dns.alidns.com = 223.5.5.5, 223.6.6.6, 2400:3200::1, 2400:3200:baba::1`

## Safety correction
The existing source contained:
```ini
[MITM]
enable = false
h2 = true
```
The candidate sets both `enable = false` and `h2 = false`. Shadowrocket documentation describes `h2 = true` as enabling HTTP/2 MitM. This change is limited to the candidate and requires device-side verification.

## Explicitly not imported
- ECS client-subnet parameters from the uploaded file.
- Tencent DoH static-IP mappings.
- Broad TLD routing rules and unverified domain rules.
- Uploaded URL Rewrite expressions (some contain malformed or incorrect patterns).
- Any MITM enablement.
- Any changes to the production DNS resolver ordering or routing architecture.

## Validation boundary
- Static text comparison only; no Shadowrocket device runtime test has been performed.
- No production file was overwritten.
- Review and approve before promoting this candidate.
