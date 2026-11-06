# Multi-source intelligence expansion

## Purpose

Extend the production automation's information-acquisition horizon beyond its current GitHub-centric rule-repository discovery. This is a staged integration, not an immediate trust grant to every provider.

## Existing pipeline

The current production path already performs GitHub repository discovery, raw GitHub rule-list assessment, source-lineage and overlap audits, deterministic admission, collection, domain review, and rule-set generation. The existing assessor and collector intentionally restrict downloads to HTTPS `raw.githubusercontent.com`. That boundary must not be weakened by adding arbitrary URLs.

## Stage 1: provider inventory (this change)

`sources/external_intelligence_catalog.json` records public provider leads across:
- open-source rule repositories;
- malware and phishing intelligence;
- DNS and certificate-derived domain observations;
- ASN, IP-prefix, and network-owner intelligence;
- official internet registry data;
- additional source-hosting platforms (GitLab and Codeberg).

`scripts/audit_external_intelligence_catalog.py` validates the inventory and appends a compact status to the Actions job summary. It performs no network requests, downloads, activation, policy classification, or repository writes. This makes the expanded source scope visible in the existing production workflow without changing rule production behavior.

## Stage 2: provider-specific adapters (required before ingestion)

Implement separate, bounded adapters for:
- GitLab and Codeberg repository discovery;
- URLhaus and OpenPhish URL/host feeds;
- Certificate Transparency queries;
- RIPEstat ASN/IP evidence;
- IANA registry metadata.

Each adapter must validate HTTPS hosts and redirects, enforce response and pagination budgets, respect provider terms/licensing, record publisher and retrieval provenance, and emit typed observations. URL observations, domain observations, certificate names, DNS records, ASN data, and IP prefixes must remain distinct types.

## Stage 3: candidate normalization and evidence review

Normalize observations into a quarantined candidate layer. Threat feeds can nominate a domain for review but must not automatically dictate REJECT. ASN, IP geography, certificate issuance, or CDN ownership must not automatically dictate DIRECT or PROXY. Require explicit policy evidence, source independence checks, lineage review, duplicate/conflict analysis, and deterministic validation.

## Stage 4: production integration

Only after adapter-specific tests and independent verification should typed observations be connected to existing candidate review and rule-set generation. New sources must establish a baseline before bulk candidate creation. Source outages or parser failures must be isolated and must not cause a mass rule change.

## Immutable boundaries

- `modules/uu.conf` and user configuration remain read-only.
- No DNS, MITM, or other user configuration changes.
- Production automation's write authority remains restricted to the authorized rule-set outputs. The catalog audit is read-only and reports only to the ephemeral Actions step summary.
- No source is activated merely because it appears in the catalog.
- Existing queue history and audit evidence are preserved.

## Acceptance gates

1. Catalog schema and host allowlist tests pass.
2. Workflow summary reports provider inventory and explicitly states that production adapters are not yet enabled.
3. Each provider adapter has fixtures, size/time limits, redirect tests, license review, provenance tests, and independent verification.
4. Candidate integration passes duplicate, lineage, conflict, and policy-evidence tests.
5. Canary run proves that no files outside the authorized rule-set write set change.
6. Only then can the relevant provider adapters be enabled.
