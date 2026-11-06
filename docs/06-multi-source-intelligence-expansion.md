# Multi-source intelligence expansion

## Purpose

Extend production information acquisition beyond GitHub rule-repository discovery while keeping evidence collection separate from routing-policy decisions.

## Existing pipeline and write boundary

The existing registered program `scripts/discover_sources.py` remains the entry point and runs in the current production discovery step under existing Watchdog/resource-lease controls. No workflow, credential, permission, or repository write path is added. The new typed evidence is stored only in the existing discovery inventory document. The assessor and collector retain their HTTPS `raw.githubusercontent.com` restrictions.

## Runtime adapters implemented

The registered discovery program performs bounded, read-only collection from:
- GitLab project search;
- Codeberg repository search;
- IANA root-zone registry.

It also implements query-driven adapters for:
- Certificate Transparency via crt.sh, only for explicit domains supplied in `EXTERNAL_INTEL_CT_DOMAINS`;
- RIPEstat network information, only for explicit resources supplied in `EXTERNAL_INTEL_RIPE_RESOURCES`.

AdGuard remains covered by the existing GitHub repository discovery path.

## Providers intentionally not fetched

- URLhaus: its current community API requires a provider-issued Auth-Key for dataset downloads. The adapter reports `awaiting_auth_key` and does not attempt unauthenticated feed downloads.
- OpenPhish: the Community Feed is subject to its published terms and is non-commercial. Because this project publishes a public repository, the feed remains disabled until its terms and permitted storage/redistribution scope are reviewed.

These providers are not counted as live adapters and no feed data is copied into the repository.

## Provenance, limits and policy separation

Each collected observation records provider identity, data type, value, source URL, source payload SHA-256, per-record SHA-256, retrieval time, optional source timestamp, and catalog activation boundary. Redirects are rejected before following if they leave the provider's HTTPS host. Responses are capped at 2 MB per provider; the aggregate run budget is 10 MB, with per-provider and total observation caps.

Repository metadata, certificate names, RIPEstat network data, and IANA TLD entries remain distinct typed observations. The adapters do not assign routing actions. ASN, IP prefix, TLD, certificate, or repository metadata cannot directly authorize DIRECT or PROXY; threat-feed membership alone cannot authorize REJECT.

Provider failures are isolated and reported per provider. CT and RIPEstat are reported as awaiting query input when no targets are supplied.

## Next integration stage

The typed observations are retained as evidence in the existing discovery inventory. They are not yet consumed by `assess_sources.py` or the deterministic domain-review engine. Before that integration, implement provider terms/license review, publisher identity verification, item-level lineage, duplicate/conflict checks, independent corroboration, deterministic review fixtures, and canary tests proving no out-of-scope writes.

## Immutable boundaries

- `modules/uu.conf` and all user-managed configuration remain unchanged.
- No DNS or MITM changes.
- No changes to assessor/collector host allowlists.
- No new workflow permissions, repository write paths, or automated source activation.
- Only the existing production writer and its current resource fencing can publish its existing allowlisted outputs.
