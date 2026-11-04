# Security and Permissions

## Protected main configuration

`modules/uu.conf` is the single authoritative user-managed configuration. Automation may read it for integrity, precedence, and conflict checks. It must never rewrite, stage, or commit it.

The baseline is tracked by Git blob SHA. An owner-approved change must be registered through the approved baseline process. Any unexplained mismatch must fail the integrity gate.

No documentation change authorizes edits to DNS, routing rules, MITM settings, or any other main-configuration content.

## Least-privilege workflows

The workflow design separates read-only auditing, publication, and notification:

- Audit jobs use read-only contents access and must not retain checkout credentials.
- Only the dedicated publication job receives contents write permission.
- The publisher consumes allowlisted, short-lived artifacts and revalidates the expected base commit.
- The publisher must not execute arbitrary repository scripts with write credentials.
- Notification jobs receive issue-writing permission only when required.

Do not bypass fail-closed rebase behavior or resolve output conflicts by blindly preferring generated content.

## Data minimization

The GitHub-only observed-domain intake accepts hostnames, not full URLs or request data. It must not accept query strings, headers, request bodies, or client identifiers. This is a manual GitHub Actions intake path, not a continuously listening server or automatic device telemetry channel.

## Optional ad-block module

The current optional module is `modules/AdBlock.sgmodule`. It maps the repository-maintained `modules/adblock/scripts/Clean_Pro.js` script. Other experimental or legacy ad-block scripts are not part of the current module mapping.

The presence of a module does not imply activation, compatibility, or device validation. Runtime changes require a separate audit, explicit scope, tests, and authorization.

## Third-party source and license handling

The repository's domain-source registry records external rule publishers and available lineage evidence. Rule data obtained from external publishers is not original project-authored data merely because it is stored or normalized in this repository.

Preserve applicable upstream license terms, copyright notices, and provenance records when retaining or redistributing third-party-derived material. Do not claim that all repository content is original without a separate code, data, history, and license audit.

## Safe change boundary

Documentation-only work must not alter scripts, workflow permissions, rule lists, source registries, generated state, or the protected configuration. Runtime changes require a separate audit, explicit scope, tests, and authorization.
