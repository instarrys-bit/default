#!/usr/bin/env python3
"""Read-only audit of a pinned external domain list against canonical ss.conf."""
from __future__ import annotations

import hashlib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from domain_rule_engine import RuleIndex, analyze_candidate, load_domain_rules

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "sources" / "baseline" / "ss.conf"
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
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Shadowrocket-domain-audit/2.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        final = urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise SystemExit(f"ERROR: unexpected download response: {response.geturl()}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise SystemExit("ERROR: source exceeds the 2 MB safety limit")
    actual_sha = git_blob_sha1(data)
    candidates = load_candidates(data)
    if len(candidates) < MIN_EXPECTED_ENTRIES:
        raise SystemExit(f"ERROR: source unexpectedly small or truncated: {len(candidates)} entries")
    rules, conditional, ignored = load_domain_rules(CONFIG)
    rule_index = RuleIndex(rules)
    apex_policy_counts = {"DIRECT": 0, "PROXY": 0, "REJECT": 0}
    apex_covered = 0
    suffix_scope_varied = []
    shadowed_same_host = []
    for domain, is_suffix in candidates:
        result = analyze_candidate(domain, is_suffix, rule_index)
        winner = result["apex_winner"]
        if winner:
            apex_covered += 1
            apex_policy_counts[winner.policy] += 1
        if is_suffix and len(result["scope_policies"]) > 1:
            winners = sorted({(r.policy, r.line, r.domain) for r in result["scope_winners"].values()})
            suffix_scope_varied.append((domain, winners))
        hit_policies = {r.policy for r in result["apex_hits"]}
        if len(hit_policies) > 1:
            shadowed_same_host.append((domain, result["apex_hits"][0], result["apex_hits"][1:]))

    report = [
        "# External domain source audit", "",
        f"- Audit time: {datetime.now(timezone.utc).isoformat()}",
        f"- Source: {SOURCE_URL}",
        f"- Git blob SHA-1: `{actual_sha}`",
        f"- Candidate entries: {len(candidates)}",
        f"- Existing unconditional DOMAIN / DOMAIN-SUFFIX rules parsed: {len(rules)}",
        f"- Conditional composite rules containing DOMAIN terms (not flattened): {len(conditional)}",
        f"- Malformed or unsupported simple domain rules held aside: {len(ignored)}",
        f"- Candidates whose apex is governed by an existing domain rule: {apex_covered}",
        "", "## Apex effective policy (first matching original rule wins)", "",
        "| Effective policy | Candidate apexes |", "|---|---:|",
    ]
    for policy, count in apex_policy_counts.items():
        report.append(f"| {policy} | {count} |")
    report += [
        "", "## Source-suffix scope policy variation", "",
        f"Candidates whose source suffix scope intersects multiple effective policies: {len(suffix_scope_varied)}",
        "",
        "These are not same-host rule collisions. They indicate that different hosts within one source suffix would be governed by different first-match rules. The source suffix is not eligible for automatic policy assignment.",
        "", "| Candidate suffix | Effective policy boundaries (policy / config line / rule domain) |",
        "|---|---|",
    ]
    for domain, winners in suffix_scope_varied:
        detail = "; ".join(f"{p} / line {line} / {rule_domain}" for p, line, rule_domain in winners)
        report.append(f"| `{domain}` | {detail} |")
    report += [
        "", "## Same-host shadowed rules", "",
        f"Candidate apexes with later matching rules carrying another policy: {len(shadowed_same_host)}",
        "",
        "The earliest matching original rule determines the effective domain-rule policy. Later matches are recorded as shadowed; they are not treated as an unresolved conflict.",
        "", "| Candidate | Winner | Later matching rules |", "|---|---|---|",
    ]
    for domain, winner, later in shadowed_same_host:
        detail = "; ".join(f"{r.policy} line {r.line} ({r.kind} {r.domain})" for r in later)
        report.append(f"| `{domain}` | {winner.policy} line {winner.line} ({winner.kind} {winner.domain}) | {detail} |")
    report += [
        "", "## Interpretation and safety boundary", "",
        "- The canonical ss.conf is authoritative; original rule order is preserved.",
        "- The effective policy for an exact host is the first matching unconditional DOMAIN or DOMAIN-SUFFIX rule.",
        "- Conditional AND/OR/NOT rules are not flattened into unconditional domain rules; protocol and other conditions remain conditional.",
        "- Source suffix entries are checked at the apex and at existing rule boundaries beneath the suffix. Different winners across subdomains are scope variation, not a same-host collision.",
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
