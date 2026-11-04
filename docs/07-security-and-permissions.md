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

The YouTube initplayback observer is documented to record hostnames locally only. It must not store full URLs or initiate network requests.

## Optional modules and third-party code

Files under `modules/` are optional. Their presence does not imply activation, compatibility, or device validation.

The repository retains the Maasea Apache 2.0 license file for the relevant derivative code. Preserve required license and provenance notices when modifying or redistributing third-party-derived code. Do not remove upstream attribution or license material.

## Safe change boundary

Documentation-only work must not alter scripts, workflow permissions, rule lists, source registries, generated state, or the protected configuration. Runtime changes require a separate audit, explicit scope, tests, and authorization.
## Optional module inventory

The documented optional assets include:

- `modules/AdBlock.sgmodule` — user-maintained ad-handling module.
- `modules/adblock/scripts/Social_Adblock.js` — social/search response handling.
- `modules/adblock/scripts/youtube_initplayback_observer.js` — local-only hostname observation for YouTube initplayback; no full URL storage or network request.
- `modules/adblock/scripts/youtube_protobuf_response_filter.js` — project-maintained derivative based on Maasea upstream code.

The former standalone `youtube-ads.sgmodule` is no longer part of the current repository layout. The presence of these files does not mean they are enabled in `uu.conf` or validated on a device.

The upstream Apache 2.0 license is retained at `modules/adblock/LICENSE-APACHE-2.0-Maasea`. Preserve its license and required notices.
