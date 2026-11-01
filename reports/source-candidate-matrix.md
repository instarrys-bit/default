# Automated source candidate matrix

This report combines parser compatibility, explicit policy evidence and README reference overlap. It does not activate sources.

| Policy | Candidate publishers | Verified publishers | Candidate files | Ready |
|---|---:|---:|---:|---|
| DIRECT | 3 | 0 | 3 | no |
| PROXY | 3 | 0 | 4 | no |
| REJECT | 1 | 0 | 3 | no |

## Same-policy source overlap

- DIRECT: Jovanykoch/rules ↔ ACL4SSR/ACL4SSR — 439 shared domains; 72.6% of smaller set; high_overlap
- DIRECT: Jovanykoch/rules ↔ Clash-FX/cn-apps-direct-domains — 83 shared domains; 69.2% of smaller set; partial_overlap
- DIRECT: ACL4SSR/ACL4SSR ↔ Clash-FX/cn-apps-direct-domains — 73 shared domains; 60.8% of smaller set; partial_overlap
- PROXY: ACL4SSR/ACL4SSR ↔ gatework/surge-rules — 3786 shared domains; 85.1% of smaller set; high_overlap
- PROXY: ACL4SSR/ACL4SSR ↔ sve1r/Rules-For-Quantumult-X — 371 shared domains; 64.6% of smaller set; partial_overlap
- PROXY: gatework/surge-rules ↔ sve1r/Rules-For-Quantumult-X — 245 shared domains; 42.7% of smaller set; partial_overlap

## Cross-policy overlap

- DIRECT / PROXY: 21 shared domain fingerprints; held for conflict review.
- DIRECT / REJECT: 7 shared domain fingerprints; held for conflict review.

## Candidate publishers

### DIRECT — Jovanykoch/rules

- Domain entries across candidate files: 6751
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: GMOogway/shadowrocket-rules, Loyalsoldier/v2ray-rules-dat, bgpeer/rules, crayonluffy/shadowrocket-rules, gatework/surge-rules, kaonimei/Shadowrocket-ADBlock-Rules, poohyeban/shadowrocket-rules, tkgeeked/clash-rules-for-shadowrocket
- Activation eligible: False
- Blockers: lineage_not_verified, possible_shared_readme_references_require_review

  - domain-only: https://raw.githubusercontent.com/Jovanykoch/rules/rel/loc-cn.list (6751 domain entries)

### DIRECT — ACL4SSR/ACL4SSR

- Domain entries across candidate files: 605
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: lineage_not_verified

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ChinaDomain.list (605 domain entries)

### DIRECT — Clash-FX/cn-apps-direct-domains

- Domain entries across candidate files: 120
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: lineage_not_verified

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/Clash-FX/cn-apps-direct-domains/main/apps-direct-domains.list (120 domain entries)

### PROXY — ACL4SSR/ACL4SSR

- Domain entries across candidate files: 7072
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: lineage_not_verified

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyGFWlist.list (6766 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyLite.list (306 domain entries)

### PROXY — gatework/surge-rules

- Domain entries across candidate files: 4451
- Policy evidence: README_policy_reference
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: GMOogway/shadowrocket-rules, Jovanykoch/rules, Loyalsoldier/v2ray-rules-dat, bgpeer/rules, crayonluffy/shadowrocket-rules, kaonimei/Shadowrocket-ADBlock-Rules, poohyeban/shadowrocket-rules, tkgeeked/clash-rules-for-shadowrocket
- Activation eligible: False
- Blockers: lineage_not_verified, possible_shared_readme_references_require_review

  - domain-only: https://raw.githubusercontent.com/gatework/surge-rules/release/gfw.txt (4451 domain entries)

### PROXY — sve1r/Rules-For-Quantumult-X

- Domain entries across candidate files: 574
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: lineage_not_verified

  - quantumult-domain-rules: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/Global.list (574 domain entries)

### REJECT — RzMY/IOS-AntiRevoke-DNS-Rules

- Domain entries across candidate files: 114
- Policy evidence: explicit_third_field
- Lineage: unverified (audited_reference_inventory)
- Possible shared README-reference peers: none found
- Activation eligible: False
- Blockers: lineage_not_verified

  - shadowrocket-domain-rules: https://raw.githubusercontent.com/RzMY/IOS-AntiRevoke-DNS-Rules/main/output/RevokeGuard_Loon.txt (38 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/RzMY/IOS-AntiRevoke-DNS-Rules/main/output/RevokeGuard_Shadowrocket.txt (38 domain entries)
  - shadowrocket-domain-rules: https://raw.githubusercontent.com/RzMY/IOS-AntiRevoke-DNS-Rules/main/output/RevokeGuard_Surge.txt (38 domain entries)

## Safety rule

Publisher count is repository-level, not file-level: several files from one repository count as one publisher. Domain overlap uses salted-free truncated SHA-256 fingerprints, not raw domain names. Near-identical source sets are grouped as one possible publisher lineage; high overlap is a correlation warning, not proof of common ancestry. README hyperlinks are only possible shared-reference signals. No candidate is activated without verified lineage and strong policy evidence.
