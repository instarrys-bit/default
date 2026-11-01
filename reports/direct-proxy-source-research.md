# DIRECT / PROXY source research

Research snapshot: 2026-10-31 UTC. This report is non-operational. None of the candidate sources below is registered in `sources/domain_sources.json` or consumed by the collector.

## Decision

Do not activate a DIRECT or PROXY source yet. The current evidence supports identifying promising source candidates, but does not establish two independent, policy-labelled publishers for either routing class. Some popular aggregate lists explicitly include one another as upstreams. Treating those aggregates as independent corroboration would inflate confidence.

## DIRECT candidates

### Hackl0us / SS-Rule-Snippet — CN.list

- URL: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/CN.list
- Publisher: `Hackl0us/SS-Rule-Snippet`
- The list contains mixed rule types, including DOMAIN-SUFFIX, DOMAIN-KEYWORD and USER-AGENT. Only exact/suffix domain entries are suitable for the current domain-only pipeline; keyword and user-agent rules must not be silently converted.
- This is a China-oriented routing snippet, but its content is not a pure list of mainland-owned domains.

### sve1r / Rules-For-Quantumult-X — China.list

- URL: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/China.list
- Publisher: `sve1r/Rules-For-Quantumult-X`
- Uses explicit `direct` policy on host/host-suffix rules, so the policy label is clearer than a country-category-only data set.
- The repository describes the rules as collected from network sources and does not provide complete item-level upstream lineage in the inspected README.
- A syntax-limited comparison of DOMAIN / DOMAIN-SUFFIX / host / host-suffix entries found 250 domains in this file and 119 in Hackl0us CN.list, with 81 shared entries (68.1% of the smaller set). High overlap is not proof of shared ancestry, but it means independence should not be assumed.

### blackmatrix7 / ios_rule_script — Shadowrocket China.list

- URL: https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/China/China.list
- The inspected README says the generated China rule is assembled from Hackl0us CN.list, GeQ1an Mainland.list, sve1r China.list, dler Domestic.yaml and other sources.
- It contains domain, keyword, user-agent and IP rules, so it is not a clean domain-only feed.
- It must not be counted as an independent corroborating publisher alongside the upstream sources it aggregates.

## PROXY candidates

### Hackl0us / SS-Rule-Snippet — foreign.list

- URL: https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/foreign.list
- Publisher: `Hackl0us/SS-Rule-Snippet`
- Contains explicit foreign-oriented domain rules, but also DOMAIN-KEYWORD rules. The current pipeline must retain only exact/suffix domain entries and must not convert keywords to domain suffixes.
- It is a curated foreign-service list, not a complete classification of every foreign domain.

### ACL4SSR / ACL4SSR — ProxyLite.list

- URL: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyLite.list
- Publisher: `ACL4SSR/ACL4SSR`
- Its README explicitly describes ProxyLite as a concise proxy list of commonly used and polluted domains.
- The file contains DOMAIN-SUFFIX and DOMAIN-KEYWORD rules, plus broad country-code suffixes such as `eu`, `hk`, `jp`, `kr`, `sg`, `tw` and `uk`. Those country suffixes are not equivalent to an item-by-item determination that every matching host should be proxied; they may also conflict with user-specific regional service choices.
- A syntax-limited comparison found 313 domain entries in ProxyLite and 272 in Hackl0us foreign.list, with 94 shared entries (34.6% of the smaller set). This is not proof of independence.

### ACL4SSR / ACL4SSR — ProxyGFWlist.list

- URL: https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyGFWlist.list
- Explicitly described by the project as a proxy list / GFW list.
- It is broader and substantially larger than ProxyLite. A GFW list is not a complete "all foreign domains" list, and its purpose is not identical to the user's desired default policy.

### blackmatrix7 / ios_rule_script — Shadowrocket Global.list

- URL: https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Shadowrocket/Global/Global.list
- Its README says it aggregates Hackl0us foreign.list, ACL4SSR ProxyGFWlist / ProxyLite, sve1r Global.list, Loyalsoldier lists, and other sources.
- It therefore cannot be counted as an independent corroborating publisher alongside those upstreams.

### sve1r / Rules-For-Quantumult-X — Global.list

- URL: https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/Global.list
- Uses explicit `OutSide` policy for host-suffix entries.
- The repository says its rules are collected from network sources; complete item-level upstream lineage was not established in this inspection.

## Geolocation data is not a routing decision

- https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/geolocation-cn describes domains with access points in mainland China. That is a useful geographic signal, but it does not itself guarantee that every listed domain should be DIRECT.
- https://raw.githubusercontent.com/v2fly/domain-list-community/master/data/geolocation-!cn describes domains without access points in mainland China. That does not mean every listed domain is blocked in mainland China or that every service should always be PROXY.
- These lists contain `include:` category references and require a domain-list parser that resolves category inheritance. They are not flat domain-only lists.

## Automation decision

1. Keep these candidate sources out of the active publication registry for now.
2. Do not count aggregate lists as independent when their README documents overlapping upstreams.
3. If a future source is registered, record publisher, source URL, exact parser, policy meaning, independence group and known upstream lineage.
4. Convert only exact and suffix domain entries. Keep keyword, user-agent, IP and non-domain rules out of the domain lists.
5. Keep the current two-source REJECT pipeline unchanged until DIRECT and PROXY each have adequate source coverage and demonstrable corroboration.

This report does not change `shadowrocket/ss.conf`, DNS, MITM, or any published rule list.


## Publication evidence hardening — 2026-11-01

The runtime now distinguishes publisher identity from source-data lineage. Every registered source must declare `lineage_status` (`verified`, `partial`, or `unverified`) and a unique `upstream_repositories` list. Declared shared upstream repositories prevent the affected sources from satisfying the configured independence minimum. Evidence contributes to confidence and automatic publication only when its lineage status is `verified`; the reviewer and final rule-set builder both enforce this requirement.

The two currently active REJECT sources are deliberately marked `unverified` because their complete upstream ancestry has not been established. They remain useful for candidate discovery and conflict/coverage checks, but their evidence cannot authorize automatic publication. The DIRECT and PROXY candidates in this report remain inactive. A lineage status may only be promoted to `verified` after a public provenance record has been reviewed and recorded in the source registry.

The scheduled workflow's Git rebase is now fail-closed: it no longer uses `-X ours`, which could silently discard conflicting automation output. A genuine conflict stops the run for a later clean recomputation.


## REJECT source lineage investigation — 2026-11-01

### sr-adblock / ad-domain-lite

Primary evidence:
- Source registry: https://github.com/ithtelab/sr-adblock/blob/main/config/sources.yaml
- Project README: https://github.com/ithtelab/sr-adblock/blob/main/README.md
- Implementation notes: https://github.com/ithtelab/sr-adblock/blob/main/docs/实现原理.md

The source registry names five domain-layer inputs: blackmatrix7/ios_rule_script, Johnshall/Shadowrocket-ADBlock-Rules-Forever, fmz200/wool_scripts, iab0x00/ProxyRules, and LOWERTOP/Shadowrocket-First. The README says the lite output contains domains identified by at least two upstream sources. The Johnshall entry in the source registry documents EasyList China, 乘风规则 and Peter Lowe as its own inputs. The published lite file does not provide per-domain attribution, so it is not possible to reconstruct which two upstreams supported each individual domain from this artifact alone.

### HaGeZi / Multi PRO

Primary evidence:
- Source inventory: https://github.com/HaGeZi/dns-blocklists/blob/main/sources.md
- Build methodology: https://github.com/HaGeZi/dns-blocklists/blob/main/FAQ.md#sources

The source inventory lists 61 GitHub repositories plus non-GitHub inputs. The FAQ states that the project evaluates and normalizes upstream inputs, combines them with independently maintained domain data, and does not copy source lists wholesale. The published Pro file does not expose per-domain provenance. Its inventory includes the Peter Lowe feed (pgl.yoyo.org), which is also named in the Johnshall lineage notes used by sr-adblock. This establishes a known shared upstream signal, although it does not prove that any particular domain in both outputs came from that shared feed.

### Independence decision

Both active REJECT sources are now recorded as `partial`, with their public provenance documents and known upstream project inventories attached. Their declared ancestry includes a known common Peter Lowe feed. The sources remain separate publishers and useful for candidate discovery and conflict checks, but they are not accepted as two fully independent evidence sources. The runtime therefore continues to exclude them from confidence scoring and automatic publication. No source is promoted to `verified` because neither output provides complete item-level lineage.

The source registry's shared-upstream hard rejection applies when both sources claim fully verified lineage. Partial lineage is recorded for audit but cannot pass the confidence gate. This prevents an incomplete inventory from either falsely proving independence or blocking safe candidate collection.


## REJECT source lineage investigation — 2026-11-01

### sr-adblock / ad-domain-lite
Primary evidence:
- https://github.com/ithtelab/sr-adblock/blob/main/config/sources.yaml
- https://github.com/ithtelab/sr-adblock/blob/main/README.md
- https://github.com/ithtelab/sr-adblock/blob/main/docs/实现原理.md

The source registry names five domain-layer inputs: blackmatrix7/ios_rule_script, Johnshall/Shadowrocket-ADBlock-Rules-Forever, fmz200/wool_scripts, iab0x00/ProxyRules, and LOWERTOP/Shadowrocket-First. The README says the lite output contains domains identified by at least two upstream sources. The Johnshall entry documents EasyList China, 乘风规则 and Peter Lowe as its own inputs. The published lite file does not provide per-domain attribution, so the exact upstream support for each individual domain cannot be reconstructed from this artifact alone.

### HaGeZi / Multi PRO
Primary evidence:
- https://github.com/HaGeZi/dns-blocklists/blob/main/sources.md
- https://github.com/HaGeZi/dns-blocklists/blob/main/FAQ.md#sources

The source inventory lists 61 GitHub repositories plus non-GitHub inputs. The FAQ states that the project evaluates and normalizes upstream inputs, combines them with independently maintained domain data, and does not copy source lists wholesale. The published Pro file does not expose per-domain provenance. Its inventory includes the Peter Lowe feed (pgl.yoyo.org), which is also named in the Johnshall lineage notes used by sr-adblock. This establishes a known shared upstream signal, although it does not prove that any particular domain in both outputs came from that shared feed.

### Independence decision
Both active REJECT sources are recorded as `partial`, with public provenance documents and known upstream project inventories attached. Their declared ancestry includes a known common Peter Lowe feed. They remain separate publishers and useful for candidate discovery and conflict checks, but are not accepted as two fully independent evidence sources. The runtime continues to exclude them from confidence scoring and automatic publication. Neither source is promoted to `verified`, because neither output provides complete item-level lineage.

The shared-upstream hard rejection applies when both sources claim fully verified lineage. Partial lineage is recorded for audit but cannot pass the confidence gate. This avoids treating an incomplete inventory as proof of independence.


## Automated source parser assessment — 2026-11-01

The scheduled source discovery now seeds these previously researched repositories and reassesses their public rule files on every run. These are candidates, not active registry entries.

### DIRECT candidates

- **sve1r China.list** — 252 Quantumult X HOST-SUFFIX rules with explicit `direct` actions. The parser ignores USER-AGENT and HOST-KEYWORD rules. The README describes domestic direct / overseas acceleration, but also states that repository contents are collected from the internet without complete item-level source attribution. Lineage remains unverified.
  - https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/China.list
- **ACL4SSR ChinaDomain.list** — 610 DOMAIN-SUFFIX entries. The file header explicitly says it is a direct-connect list. No IP/CIDR or keyword rules are converted.
  - https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ChinaDomain.list
- **Hackl0us CN.list** — 119 DOMAIN-SUFFIX entries plus 8 DOMAIN-KEYWORD and 2 USER-AGENT rules. The latter rule types are ignored. The file name alone is not treated as a routing-policy action.
  - https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/CN.list

### PROXY candidates

- **sve1r Global.list** — 856 HOST-SUFFIX rules with explicit `OutSide` actions, normalized to PROXY. HOST-KEYWORD and USER-AGENT entries are ignored. Publisher-level upstream lineage is incomplete.
  - https://raw.githubusercontent.com/sve1r/Rules-For-Quantumult-X/main/Rules/Region/Global.list
- **ACL4SSR ProxyLite.list** — 311 DOMAIN-SUFFIX and 9 DOMAIN entries; the header explicitly says proxy list. 26 DOMAIN-KEYWORD and 84 IP/CIDR entries are ignored.
  - https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyLite.list
- **ACL4SSR ProxyGFWlist.list** — a much larger proxy-labelled list; domain entries can be extracted, but its purpose is a GFW/proxy list, not a complete inventory of every foreign domain.
  - https://raw.githubusercontent.com/ACL4SSR/ACL4SSR/master/Clash/ProxyGFWlist.list
- **Hackl0us foreign.list** — 272 DOMAIN-SUFFIX and 10 DOMAIN-KEYWORD entries. It is not treated as an exhaustive foreign-domain set, and the file name alone is not a policy action.
  - https://raw.githubusercontent.com/Hackl0us/SS-Rule-Snippet/main/Rulesets/Surge/Basic/foreign.list

### Independence and activation status

- sve1r explicitly describes its rules as collected from the internet; the README does not provide complete item-level provenance.
- ACL4SSR documents the routing semantics of its ChinaDomain and ProxyLite lists, but the published list files do not provide complete per-domain upstream attribution.
- Hackl0us maintains a curated rule repository, but the CN / foreign files do not themselves encode routing actions or provide complete per-domain lineage.
- blackmatrix7 is an aggregator and is not counted as independent alongside its documented upstream sources.
- Goahead-zfc provides a useful DIRECT and PROXY candidate pair with explicit README RULE-SET references, but it is one publisher and its domestic-apps list includes IP rules that are ignored by the domain-only pipeline.

No DIRECT or PROXY source is activated from this assessment. The existing automatic evidence gate requires two independent, verified source publishers for each policy. Publisher labels, list names, README policy claims, and separate URLs are not proof of independent data lineage. The next automated step is to compare these candidates' upstream inventories and domain-level overlap, then keep only sources whose provenance and policy semantics can be established without guessing.
