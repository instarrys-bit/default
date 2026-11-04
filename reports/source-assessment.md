# Automated source assessment

- Rule-list files assessed: **1**
- This stage checks syntax and explicit policy claims only. It never activates sources.
- Keyword, IP/CIDR and ASN rules are counted as ignored; they are never converted into domains.

| Repository | Parser candidate | Policy candidate | Domain entries | Drift | Evidence |
|---|---|---|---:|---|---|
| ZingyAwesome/easylists-for-pihole | domain-only | — | 40558 | baseline_initialized | none |

## Source update drift

- New source files: 1
- Changed source files: 0
- Added domain entries: 40558
- Removed domain entries: 0
- Policy changes: 0

## Assessment details

### ZingyAwesome/easylists-for-pihole

- URL: https://raw.githubusercontent.com/ZingyAwesome/easylists-for-pihole/master/easyprivacy.txt
- SHA-256: c811223a5b962adf64c9e8f8adade9220098af8e6929238c04b1b97fdbf7fd6b
- Exact DOMAIN: 0; DOMAIN-SUFFIX: 0; Adblock: 0; domain-only: 40558; duplicate lines: 0
- Ignored non-domain rules: DOMAIN-KEYWORD 0; IP/CIDR/ASN 0
- Explicit action counts: {}
- Policy evidence: none; candidate: none

## Activation gate

A parser candidate is not a trusted source. Activation still requires declared policy semantics, independent publishers, lineage checks, parser tests, stable update history, and all per-policy confidence gates. This report is advisory and cannot alter sources/domain_sources.json.
