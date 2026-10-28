# Shadowrocket configuration

This repository is the source of truth for the maintained Shadowrocket configuration.

## Subscription URL

After `shadowrocket/ss.conf` is committed, use this raw URL in Shadowrocket:

`https://raw.githubusercontent.com/instarrys-bit/default/main/shadowrocket/ss.conf`

In Shadowrocket, add/import the URL as a remote configuration or subscription, then use its update/refresh action to pull future commits. GitHub `main` is the delivery branch; changes committed to this file become available at the same URL. The app's refresh interval and exact menu labels depend on the installed Shadowrocket version.

## Maintenance rules

- Keep the canonical config at `shadowrocket/ss.conf`; preserve the URL to avoid needing to re-add the subscription.
- Before each change, review the current file and compare the diff; do not overwrite the whole configuration from an older copy.
- Preserve the existing DNS routing constraints, rule-layer order, Apple-specific handling, and domain-by-domain evidence notes unless a reviewed change explicitly requires otherwise.
- Validate section headers, rule syntax, duplicate/conflicting rules, DNS policy consistency, and final catch-all rules before committing.
- Test on-device after refresh. A successful GitHub commit only verifies delivery, not that Shadowrocket accepts the config or that traffic behaves as intended.
- Do not put proxy credentials, private keys, subscription tokens, or other secrets in this public repository.

## Change workflow

1. Inspect the current version and identify the exact intended changes.
2. Make a minimal, reviewable diff and explain the reason/evidence for each routing or DNS change.
3. Run static checks and review the diff.
4. Commit to `main` only after the change is approved.
5. Refresh the remote configuration in Shadowrocket and test the affected traffic paths on the device.

## Status

The repository was initially empty. The configuration file still needs to be added at `shadowrocket/ss.conf` before the subscription URL above can be used.