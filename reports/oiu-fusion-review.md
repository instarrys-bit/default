# oiu.conf Merge Review

Date: 2026-11-02

## Scope and authority
- Reference upload: `oiu.conf`
- Production base: `shadowrocket/ss.conf`
- Production base blob SHA observed during review: `a6b2f0e6e41da13572dfca8e8119212118df5bcb`
- This review is not authorization to modify or publish the production configuration.
- The production `shadowrocket/ss.conf` remains untouched.

## Critical preservation rule
**Do not edit the [MITM] section.** Do not enable it, disable it, change its HTTP/2 option, or copy MITM settings from the reference file. The user's active/device configuration may differ from the repository snapshot. Therefore this review deliberately makes no claim about the active MITM state and the patch contains no MITM directives.

The older full candidate `candidates/ss.conf.oiu-fusion-candidate` is superseded and must not be used as a deployment candidate: it altered the MITM section. It is retained as historical material and is not modified by this review.

## Accepted as a narrowly scoped candidate
One additive [Host] entry is proposed:

```ini
dns.alidns.com = 223.5.5.5, 223.6.6.6, 2400:3200::1, 2400:3200:baba::1
```

Rationale:
- The reference file contains this resolver bootstrap mapping.
- The production [Host] section does not currently contain this exact mapping.
- It does not change DNS resolver ordering, DNS routing policy, or the three traffic policies.
- It is a candidate addition only; device-side validation is still required.

## Not accepted
- Tencent DoH static-IP mappings for `doh.pub` and `sm2.doh.pub`: not imported; retain the hostname-based DoH endpoints already configured.
- ECS/client-subnet parameters: not imported because they disclose additional client-network location metadata and are not needed for the stated design.
- Broad TLD rules (`.xyz`, `.ai`, `.io`, `.app`, `.dev`): not imported; TLD alone is insufficient to classify every domain as PROXY.
- `sentry.io -> PROXY`: conflicts with the existing user requirement to block Sentry.
- Unverified one-off DIRECT/PROXY domain rules: send through the existing candidate review pipeline, not into the user-owned main config.
- Uploaded URL Rewrite expressions: not imported; several differ from the production expressions and include suspicious/incorrect targets or patterns.
- Router hostname mappings: not imported wholesale; device/router-specific entries need confirmation against the active LAN/router environment.
- MITM settings: absolutely untouched.

## Existing content already present
- `mb.cmbimg.com.queniuqy.com = 122.156.130.17` is already present in the production [Host] section; do not duplicate it.
- Existing resolver bootstrap entries for Google, Quad9 and Cloudflare are already present; do not duplicate them.
- Existing telemetry sinkhole Host entries from the reference file are already present; no duplicate import is needed.

## Validation and deployment boundary
- This is a static text review; no Shadowrocket runtime test has been performed.
- No edit has been made to `shadowrocket/ss.conf`.
- The additive patch is separate and must be reviewed before any manual promotion.
- Preserve all existing settings outside the exact approved additive line, especially the entire [MITM] section.
