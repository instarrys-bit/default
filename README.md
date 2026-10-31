# Shadowrocket configuration

This repository is the canonical, version-controlled source for the maintained Shadowrocket configuration.

## Remote configuration URL

`https://raw.githubusercontent.com/instarrys-bit/default/main/shadowrocket/ss.conf`

Add that URL in Shadowrocket as a remote configuration (or URL-based configuration import, depending on app version). After a change is committed to `main`, refresh/update the remote configuration in Shadowrocket to fetch the new version. The URL is stable; do not rename or move `shadowrocket/ss.conf` without intentionally migrating the subscription.

## Source and scope

- Canonical file: `shadowrocket/ss.conf`
- Delivery branch: `main`
- Current file is based on the user-provided `ss.conf`, uploaded without intentional rule or DNS edits.
- GitHub history records every committed version and provides diffs for maintenance review.

## Maintenance contract

1. **Audit first:** read the current repository version and inspect relevant logs/evidence before planning changes.
2. **Plan before editing:** state the exact proposed changes and rationale; do not make broad rewrites from an older local copy.
3. **Preserve architecture:** retain the DNS path constraints, six-layer rule ordering, domain-by-domain analysis, Apple-specific strategy, and existing policy intent unless a reviewed change explicitly calls for a change.
4. **Minimize diffs:** change only the necessary lines and explain the evidence and expected effect.
5. **Validate before commit:** check section headers, rule syntax, duplicate/conflicting rules, DNS policy consistency, catch-all ordering, and the diff. Static checks cannot prove that Shadowrocket will accept the config or that network traffic behaves correctly.
6. **Device verification:** after refreshing the URL, test the affected traffic paths and inspect Shadowrocket logs. Record what was and was not tested.
7. **Protect secrets:** this repository is public. Never commit proxy credentials, private keys, subscription tokens, private IP/account details, or diagnostic logs containing sensitive information.

## External domain rule selector

- External domain lists are untrusted candidate data only; upstream policy directives are never imported.
- `scripts/domain_rule_engine.py` is the shared parser for both audit and selection. It reads the canonical `[Rule]` section in file order and reads the policy from the third comma-separated field; trailing options such as `no-resolve` are not mistaken for policy.
- For an exact host, the first matching unconditional `DOMAIN` or `DOMAIN-SUFFIX` rule determines the effective domain-rule policy. Later matching rules are recorded as shadowed, not treated as unresolved conflicts.
- Conditional `AND` / `OR` / `NOT` rules are counted separately and are not flattened into unconditional domain policy.
- A source suffix is checked at its apex and at existing rule boundaries beneath it. If different subdomains resolve to different first-match policies, that suffix is quarantined for review rather than assigned one policy.
- Candidates already governed by the canonical config are excluded; external policy never overrides the original configuration.
- New policy assignment requires an explicit entry in `sources/policy_approvals.json` with an evidence note.
- The selector emits only exact `DOMAIN,<domain>,DIRECT|PROXY|REJECT` lines into `reports/approved-domain-rules.list`; it does not patch `ss.conf`.
- A source leading dot is not permission to generate a broader `DOMAIN-SUFFIX` rule.
- Empty approvals mean zero new rules are authorized. Do not populate approvals without domain-specific evidence and review.

## Typical update procedure

- Inspect current `main` and the relevant evidence.
- Propose a minimal diff and wait for approval before changing routing/DNS behavior.
- Run available static checks and review the diff.
- Commit the approved change to `main`.
- Refresh the remote configuration in Shadowrocket and test on-device.

## Current status

- [x] Initial configuration uploaded to `shadowrocket/ss.conf`.
- [x] Stable raw URL established for remote import/update.
- [ ] Shadowrocket import/refresh and real-device traffic tests remain to be performed by the user; a successful GitHub upload does not verify device behavior.
