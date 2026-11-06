# Multi-source intelligence expansion

## Purpose

Extend production information acquisition beyond GitHub rule-repository discovery while keeping evidence collection separate from routing-policy decisions.

## Existing pipeline and write boundary

The existing registered program `scripts/discover_sources.py` remains the entry point. It already runs in the production source-discovery step under the existing Watchdog/resource-lease controls. This change adds no workflow, credential, write path, or permission. It extends the existing discovery inventory document only; it does not add new repository paths to the write set.

The rule assessor and domain collector retain their HTTPS `raw.githubusercontent.com` restrictions. Those restrictions are not weakened.

## Runtime adapters now implemented

The existing discovery program collects bounded, typed observations from:
- URLhaus recent malware URL feed;
- OpenPhish feed;
- GitLab project search;
- Codeberg repository search;
- IANA root-zone registry.

It also implements query-driven adapters for:
- Certificate Transparency via crt.sh, requiring explicit `EXTERNAL_INTEL_CT_DOMAINS`;
- RIPEstat network information, requiring explicit `EXTERNAL_INTEL_RIPE_RESOURCES`.

AdGuard remains covered by the existing GitHub discovery path.

Every observation records provider identity, data type, value, source URL, source payload SHA-256, per-record SHA-256, retrieval time, optional source timestamp, and the catalog activation boundary. Redirects are constrained to the same HTTPS provider host. Each response is capped at 2 MB; the aggregate run budget is 10 MB, with per-provider and total observation caps.

## Evidence types and policy separation

URLhaus URLs, OpenPhish URLs, repository metadata, certificate names, RIPEstat network data, and IANA TLD entries remain distinct typed observations. The adapters do not assign routing actions. Threat-feed membership alone does not authorize REJECT; ASN, IP prefix, TLD, or certificate evidence does not authorize DIRECT or PROXY.

Provider failures are isolated and reported per provider. CT and RIPEstat are explicitly reported as awaiting query input when no targets are supplied.

## Next integration stage

The new observations are retained in the existing discovery inventory as evidence only. They are not yet consumed by `assess_sources.py` or the deterministic domain-review engine. Before that integration, implement:
1. provider-specific license/terms review and publisher identity verification;
2. normalization into quarantined domain candidates with exact item-level provenance;
3. lineage, duplicate, conflict, and independent-source checks;
4. deterministic review fixtures and canary runs proving no out-of-scope writes;
5. explicit acceptance gates before any new observation can influence the three rulesets.

## Immutable boundaries

- `modules/uu.conf` and all user-managed configuration remain unchanged.
- No DNS or MITM changes.
- No changes to the assessor/collector host allowlists.
- No new workflow permissions, repository write paths, or automated source activation.
- Only the existing production writer and its current resource fencing can publish existing allowlisted outputs.
