# External domain source scope audit

- Audit time: 2026-11-03T09:55:39.687505+00:00
- Source: https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list
- Git blob SHA-1: `ec23c2d1280ea4a59717816716b8ccb569dac624`
- Candidate entries: 56516
- Explicit DIRECT/PROXY DOMAIN / DOMAIN-SUFFIX config rules: 1200
- Conditional composite rules (not evaluated for precedence): 0
- Malformed or unsupported simple domain rules held aside: 0
- Fully covered candidate scopes: 18884
- Partially intersecting suffix candidates: 1
- No full-scope coverage: 37631

## Full-scope coverage by configured policy

| Config policy | Candidate scopes |
|---|---:|
| DIRECT | 1689 |
| PROXY | 17189 |
| REJECT | 0 |

## Mixed-policy full-scope coverage

Candidates covered by explicit scopes carrying more than one policy: 6

| Candidate | Covering config scopes |
|---|---|
| `aliapp.org` | DOMAIN-SUFFIX,aliapp.org => DIRECT; DOMAIN-SUFFIX,org => PROXY |
| `app-monitor.ele.me` | DOMAIN-SUFFIX,ele.me => DIRECT; DOMAIN-SUFFIX,me => PROXY |
| `client-api.ele.me` | DOMAIN-SUFFIX,ele.me => DIRECT; DOMAIN-SUFFIX,me => PROXY |
| `grand.ele.me` | DOMAIN-SUFFIX,ele.me => DIRECT; DOMAIN-SUFFIX,me => PROXY |
| `mobile-pubt.ele.me` | DOMAIN-SUFFIX,ele.me => DIRECT; DOMAIN-SUFFIX,me => PROXY |
| `newton-api.ele.me` | DOMAIN-SUFFIX,ele.me => DIRECT; DOMAIN-SUFFIX,me => PROXY |

## Partial overlaps / narrower exceptions

Candidates with a narrower or partial config overlap: 1

| Candidate scope | Intersecting config scopes |
|---|---|
| `cloudflareinsights.com` | DOMAIN,static.cloudflareinsights.com => PROXY |

## Interpretation and safety boundary

- This report records scope coverage and partial intersections only; it does not infer a winning policy.
- A child exact or child-suffix exception does not fully cover a broader source suffix candidate.
- Mixed-policy coverage is reported without selecting a winner.
- Conditional rules are counted but not evaluated here; the deterministic reviewer applies its separate conservative REVIEW hold.
- No external policy is inferred, and no candidate is imported into ss.conf.
- No existing rule, DNS setting, node, rule order, or subscription is modified.
- The source hash is recorded each run; additions and removals are compared against the rolling snapshot by the collector. Format or size anomalies fail closed.
