# Rule Review and Admission

## Allowed policy scope

The publisher is restricted to exactly three policies: `DIRECT`, `PROXY`, and `REJECT`. Do not introduce additional routing categories. Do not infer policy from a domain name, top-level domain, IP geolocation, or DNS response.

## Per-domain evidence

A domain requires current, consistent evidence from at least two distinct publishers and distinct source groups before publication. Multiple files from one publisher do not count as multiple publishers.

Source lineage is recorded and disclosed. A `partial` or `unverified` lineage label is not, by itself, an automatic veto. However, declared shared upstream repositories prevent the affected sources from satisfying the independence minimum. Source overlap is a correlation warning, not proof of shared ancestry or proof that a domain is incorrect.

## Hold conditions

Do not publish candidates with:

- Evidence from only one eligible publisher.
- Insufficient or inconsistent policy evidence.
- The same domain assigned to multiple policies.
- Conflicts with existing rules or the authoritative main configuration.
- Conditional-rule overlap or unsupported rule scope.
- Protected-domain or critical-service risk matches.
- Parser errors, malformed entries, or unresolved safety checks.

Single-source candidates may remain under observation. Cross-policy conflicts must be isolated, never resolved by source ordering.

## Supported source formats

- `domain-only`, including explicitly enabled leading-dot suffix mode.
- `adblock-domain-rules`.
- `shadowrocket-domain-rules`.
- `quantumult-domain-rules`.

Parsers extract supported domain entries only. They must not convert `DOMAIN-KEYWORD`, `USER-AGENT`, IP/CIDR, ASN, process, or other non-domain rules into domain entries. Broad single-label suffixes are excluded and duplicates are deduplicated.

If a source embeds an explicit action, it must match the registry classification or an explicit action map. Each source declares its policy, publisher, independence group, parser, role, HTTPS raw URL, scoring weight, and policy-evidence type.

## Exact and suffix scope

Exact domains and suffix rules may be published. A `DOMAIN-SUFFIX` candidate requires at least two independent publishers explicitly declaring the same suffix scope, followed by scope-conflict, conditional-rule, protected-domain, and configuration-priority checks. Never broaden an exact domain into a suffix by inference.

## Main-configuration precedence

The user-maintained `modules/uu.conf` is authoritative. Automation may read it and compare its recorded Git blob SHA. Only an owner-approved baseline change may update the approved baseline metadata. The automation must never modify the configuration itself.

## Review ledger

The deterministic review ledger is maintained under `sources/`. Retired Gemini/GPT review workflows must not be reintroduced into the automated review path.