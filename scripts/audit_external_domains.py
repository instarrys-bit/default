#!/usr/bin/env python3
"""Read-only scope-coverage audit of a pinned external domain list against ss.conf."""
from __future__ import annotations

import hashlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from domain_rule_engine import load_domain_rules
from audit_ruleset_config_overlap import scope_covers_candidate, scope_intersects

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
SOURCE_URL = "https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list"
MIN_EXPECTED_ENTRIES = 50000
MAX_BYTES = 30_000_000
OUTPUT = ROOT / "reports" / "external-domain-audit.md"


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load_candidates(data: bytes):
    candidates = []
    seen = set()
    for number, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if value != raw or any(ch.isspace() for ch in value):
            raise ValueError(f"invalid whitespace at source line {number}")
        is_suffix = value.startswith(".")
        domain = value[1:] if is_suffix else value
        labels = domain.split(".")
        if (len(domain) > 253 or len(labels) < 2 or
            any(not label or len(label) > 63 or label.startswith("-") or
            label.endswith("-") or not label.replace("-", "").isalnum() or
            not label.isascii() for label in labels)):
            raise ValueError(f"invalid domain at source line {number}: {raw!r}")
        key = domain.lower()
        if key in seen:
            raise ValueError(f"duplicate candidate at source line {number}: {key}")
        seen.add(key)
        candidates.append((key, is_suffix))
    return candidates


def main() -> int:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Shadowrocket-domain-audit/3.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        final = urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise SystemExit(f"ERROR: unexpected download response: {response.geturl()}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit("ERROR: source exceeds the configured byte limit")
    actual_sha = git_blob_sha1(data)
    candidates = load_candidates(data)
    if len(candidates) < MIN_EXPECTED_ENTRIES:
        raise SystemExit(f"ERROR: source unexpectedly small or truncated: {len(candidates)} entries")

    rules, conditional, ignored = load_domain_rules(CONFIG)
    covered_by_policy = {"DIRECT": 0, "PROXY": 0, "REJECT": 0}
    mixed_coverage = []
    partial_overlaps = []
    uncovered = 0
    for domain, is_suffix in candidates:
        scope = "suffix_candidate" if is_suffix else "exact_candidate"
        full_matches = [
            rule for rule in rules
            if scope_covers_candidate(scope, domain, rule.kind, rule.domain)
        ]
        partial_matches = [
            rule for rule in rules
            if scope_intersects(scope, domain, rule.kind, rule.domain)
            and not scope_covers_candidate(scope, domain, rule.kind, rule.domain)
        ]
        if full_matches:
            policies = {rule.policy for rule in full_matches}
            if len(policies) == 1:
                covered_by_policy[next(iter(policies))] += 1
            else:
                mixed_coverage.append((domain, sorted({
                    (rule.kind, rule.domain, rule.policy) for rule in full_matches
                })))
        elif partial_matches:
            partial_overlaps.append((domain, sorted({
                (rule.kind, rule.domain, rule.policy) for rule in partial_matches
            })))
        else:
            uncovered += 1

    report = [
        "# External domain source scope audit", "",
        f"- Audit time: {datetime.now(timezone.utc).isoformat()}",
        f"- Source: {SOURCE_URL}",
        f"- Git blob SHA-1: `{actual_sha}`",
        f"- Candidate entries: {len(candidates)}",
        f"- Explicit DOMAIN / DOMAIN-SUFFIX config rules: {len(rules)}",
        f"- Conditional composite rules (not evaluated for precedence): {len(conditional)}",
        f"- Malformed or unsupported simple domain rules held aside: {len(ignored)}",
        f"- Fully covered candidate scopes: {sum(covered_by_policy.values()) + len(mixed_coverage)}",
        f"- Partially intersecting suffix candidates: {len(partial_overlaps)}",
        f"- No full-scope coverage: {uncovered}",
        "", "## Full-scope coverage by configured policy", "",
        "| Config policy | Candidate scopes |", "|---|---:|",
    ]
    for policy, count in covered_by_policy.items():
        report.append(f"| {policy} | {count} |")
    report += [
        "", "## Mixed-policy full-scope coverage", "",
        f"Candidates covered by explicit scopes carrying more than one policy: {len(mixed_coverage)}",
        "", "| Candidate | Covering config scopes |", "|---|---|",
    ]
    for domain, matches in mixed_coverage:
        detail = "; ".join(f"{kind},{rule_domain} => {policy}" for kind, rule_domain, policy in matches)
        report.append(f"| `{domain}` | {detail} |")
    report += [
        "", "## Partial overlaps / narrower exceptions", "",
        f"Candidates with a narrower or partial config overlap: {len(partial_overlaps)}",
        "", "| Candidate scope | Intersecting config scopes |", "|---|---|",
    ]
    for domain, matches in partial_overlaps:
        detail = "; ".join(f"{kind},{rule_domain} => {policy}" for kind, rule_domain, policy in matches)
        report.append(f"| `{domain}` | {detail} |")
    report += [
        "", "## Interpretation and safety boundary", "",
        "- This report records scope coverage and partial intersections only; it does not infer a winning policy.",
        "- A child exact or child-suffix exception does not fully cover a broader source suffix candidate.",
        "- Mixed-policy coverage is reported without selecting a winner.",
        "- Conditional rules are counted but not evaluated here; the deterministic reviewer applies its separate conservative REVIEW hold.",
        "- No external policy is inferred, and no candidate is imported into ss.conf.",
        "- No existing rule, DNS setting, node, rule order, or subscription is modified.",
        "- The source hash is recorded each run; additions and removals are compared against the rolling snapshot by the collector. Format or size anomalies fail closed.", "",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = "\n".join(report)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
