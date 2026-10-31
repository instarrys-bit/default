# External domain source audit — ithtelab/sr-adblock

- Audit date: 2026-10-31
- Scope: domain data files only; no modules, scripts, MITM, Rewrite, DNS, proxy, or configuration files are approved for import.
- Result: **candidate data only; not imported into the canonical Shadowrocket config.**

## Files inspected

| Release file | Git blob SHA-1 | Size observed | Active entries | Unique entries | Format result |
|---|---|---:|---:|---:|---|
| `ruleset/ad-domain-lite.list` | `ec23c2d1280ea4a59717816716b8ccb569dac624` | 1,103,926 bytes | 56,516 | 56,516 | 56,516 entries passed the conservative hostname syntax check |
| `ruleset/ad-domain.list` | `842f2d547cb6bb6034560215b2040792d07c21af` | 5,720,648 bytes | 283,117 | 283,117 | 3 entries contain underscores and require manual review |
| `ruleset/ad-rule.list` | `40a262be5c54d0d10d992f4f91a0579874cbcf97` | 14,983 bytes | 387 | 387 | Not a pure-domain file; contains DOMAIN-KEYWORD, IP-CIDR, IP-CIDR6, URL-REGEX and USER-AGENT rules |

The three nonconforming entries in the full domain list are:

- `.ad-cdn_core.cctv.com`
- `.ad_core.cctv.com`
- `.ad_m.cctv.com`

They were not silently normalized or accepted as ordinary hostnames.

## Scope and content findings

1. `ad-domain-lite.list` is a comment header followed by bare domain entries. The inspected file had no duplicate active entries and no URL, IP literal, wildcard, comma-delimited policy, script syntax, or malformed hostname under the conservative ASCII hostname check.
2. `ad-domain.list` is also a domain-oriented list, but the three underscore labels above fail the conservative hostname check. They must be held for manual decision, not auto-corrected.
3. `ad-rule.list` is explicitly a mixed rule file. It is rejected in full for this project.
4. The source README and `config/sources.yaml` describe multiple source formats, including domain sets, generic rulesets, and Surge configuration rules. Only a separately validated bare-domain data file is even eligible for consideration.
5. The upstream repository contains many module sources and describes MITM, HTTPDNS, Rewrite, JavaScript, certificate and other optional modules. None are in scope and none were imported.

## Provenance and licensing caveats

The upstream `NOTICE` identifies these domain-layer contributors:

- blackmatrix7 / ios_rule_script — GPL-2.0
- Johnshall / Shadowrocket-ADBlock-Rules-Forever — CC-BY-SA-4.0
- fmz200 / wool_scripts — license not declared
- iab0x00 / ProxyRules — no license file
- LOWERTOP / Shadowrocket-First — license not declared

The lite list is an aggregated output from these sources. The upstream says it uses entries appearing in at least two trusted sources, but this audit did not independently verify the full derivation or independence of every upstream contributor. The aggregation therefore does not remove attribution, share-alike, or no-license concerns.

**Do not mirror or republish the aggregated list as a public artifact until its applicable license obligations have been reviewed.** Fetching a public file does not itself grant redistribution rights.

## Policy boundary

- No external entry has been assigned DIRECT, PROXY, or REJECT by this audit.
- The upstream's suggested REJECT usage is not adopted.
- No external domain has been added to `shadowrocket/ss.conf`.
- No DNS settings, nodes, subscriptions, scripts, modules, MITM settings, rewrite rules, or other configuration content were imported.
- The existing canonical configuration remains unchanged.

## Recommendation

If proceeding, use `ad-domain-lite.list` only as an untrusted candidate domain dataset. Pin the observed upstream blob SHA, fetch it in a read-only GitHub Actions job, validate every entry, and produce a diff/report artifact. Any new domain still requires a separate locally governed policy decision. Keep the actual configuration publication disabled until the policy mapping and license questions are resolved.

## Validation limits

This was a static text audit of the named release artifacts and upstream documentation. It does not establish that every listed domain is malicious, that every candidate should be blocked, or that the list is safe to apply wholesale. It does not replace application-level testing or Shadowrocket device testing.
