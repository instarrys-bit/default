# Source Governance

## Registry requirements

The source registry defines enabled feeds and their interpretation. Each registered source declares:

- Policy classification.
- Publisher identity and independence group.
- Parser format and source role.
- HTTPS raw-content URL.
- Scoring weight and policy-evidence type.
- Lineage status and declared upstream repositories.

A repository name or README label such as China, Global, Direct, or Proxy is not sufficient policy evidence.

## Collection roles and snapshots

The collector is registry-driven. It fetches enabled sources, uses only explicitly supported parsers, verifies each source independently, and stores a snapshot under `data/source_snapshots/<source-id>.txt`.

Only sources marked as primary candidate sources enqueue newly observed domains. Other sources provide corroborating evidence but do not independently enqueue candidates. A domain observed under more than one policy is held as a policy conflict.

New sources normally establish a baseline without bulk-enqueueing their initial contents. A primary source explicitly marked `bootstrap_enqueue` may seed its initial domain set once; subsequent runs enqueue additions only. Corroboration sources never enqueue candidates by themselves.

## Discovery and assessment

Automated discovery searches public repositories and candidate feeds for possible rule sources. Discovery is non-activating: search results, repository names, README claims, and candidate URLs are leads, not approval.

Assessment checks supported domain syntax, exact/suffix counts, ignored non-domain entries, and explicit policy evidence. Mixed or incomplete evidence remains unclassified. Discovery and assessment inventories are stored under `sources/` and `reports/`.

The candidate matrix joins parser assessments, policy evidence, and possible shared references. It reports publisher counts, eligible evidence counts, candidate blockers, source-set overlap, near-duplicates, and cross-policy conflicts. Domain-set comparisons may use truncated SHA-256 fingerprints rather than exposing raw inventories. High overlap is a warning, not automatic deletion or a lineage verdict.

## Source ancestry audit

The ancestry audit examines registered public provenance documents and referenced repositories, compares discovered references with registry declarations, and reports new or stale declarations and shared upstreams. It does not automatically mark lineage as verified. Repository-level link discovery is not proof of per-domain provenance.

Failure to retrieve or parse a required registered provenance document must fail the audit closed rather than silently treating missing evidence as independence.

## Automatic admission

Source admission is deterministic and does not use AI review. Documented checks include strong explicit policy evidence, a non-archived publisher, supported parser compatibility, at least 100 unique domains, an unchanged second observation, and a fresh fetch whose SHA-256 matches the assessed bytes. The exact bytes are parsed with the production collector before registry activation.

Parser failures, source drift, weak policy claims, and archived publishers remain held. Lineage uncertainty and shared README references are recorded as warnings unless a declared shared upstream invalidates the independence requirement. Newly admitted sources are persisted in the registry and activation log.

## Candidate families

Source research has included ACL4SSR, Clash-FX, sve1r, and ad-block domain feeds. Candidate names and historical seed lists do not guarantee that every feed remains enabled or approved. Inspect the current registry and source reports before describing active sources.
## Discovery and assessment implementation

The documented components include:

- `scripts/discover_sources.py` — searches public GitHub repositories for Shadowrocket rules, China-domain lists, proxy/direct domain lists, geosite, and ad-block sources. It inspects repository README files for repository-owned `.list`, `.txt`, and `.conf` URLs. Results are stored in `sources/discovered_sources.json` and `reports/source-discovery.md`.
- `scripts/assess_sources.py` — checks supported domain syntax, exact/suffix counts, and explicit policy evidence. It stores `sources/source_assessments.json` and `reports/source-assessment.md`.
- `scripts/build_source_candidates.py` — joins parser assessments, policy evidence, and possible shared README references. It stores `sources/source_candidates.json` and `reports/source-candidate-matrix.md`.
- `scripts/audit_policy_source_overlap.py` — computes same-policy source overlap and cross-policy conflicts. It stores `sources/policy_source_overlap.json` and `reports/policy-source-overlap.md`.
- `scripts/audit_source_lineage.py` — audits provenance references and writes `reports/source-lineage-audit.json`.
- `scripts/auto_activate_sources.py` — applies deterministic source-admission gates and persists approved registry changes and activation records.

A GitHub API outage during discovery retains the previous inventory and must not prevent the independent deterministic audit. Candidate discovery and assessment are non-activating stages.

## Discovery seed feeds

Historical discovery leads have included Hackl0us, sve1r, ACL4SSR, blackmatrix7, Loyalsoldier, Jovanykoch, gatework, and Clash-FX. These are leads, not automatically approved active sources. Policy semantics, parser compatibility, publisher identity, lineage, overlap, and update drift must be reassessed.

Multiple files from one repository count as one publisher. Candidate-matrix overlap fingerprints are correlation signals, not proof of shared ancestry and not a reason to mass-discard domains.

## Current registered policy examples

The documented source families include ACL4SSR ChinaDomain and Clash-FX cn-apps-direct-domains for DIRECT; ACL4SSR ProxyLite and sve1r Global for PROXY; and sr-adblock-domain-lite and HaGeZi Pro for REJECT. The active registry remains authoritative: this list is a description of the documented design, not a live assertion that every feed is currently enabled.
