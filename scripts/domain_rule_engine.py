#!/usr/bin/env python3
"""Shared, ordered parser for the canonical Shadowrocket domain rules.

Only unconditional DOMAIN and DOMAIN-SUFFIX rules are used to determine a
host's domain-rule winner. Composite rules (AND/OR/NOT), URL rules, IP rules,
and other match dimensions are reported separately and never flattened into
unconditional domain policy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

POLICIES = {"DIRECT", "PROXY", "REJECT"}
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)


@dataclass(frozen=True)
class DomainRule:
    kind: str
    domain: str
    policy: str
    line: int
    raw: str


def load_domain_rules(config_path: Path):
    if not config_path.is_file():
        raise ValueError("canonical shadowrocket/ss.conf is missing")
    content = config_path.read_text(encoding="utf-8")
    if content.count("[Rule]") != 1 or content.count("[Host]") != 1:
        raise ValueError("cannot uniquely isolate canonical [Rule] section")
    start = content.index("[Rule]") + len("[Rule]")
    end = content.index("[Host]", start)
    block = content[start:end]
    rules = []
    conditional_domain_lines = []
    ignored_domain_lines = []
    for line_no, raw in enumerate(block.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [part.strip() for part in line.split(",")]
        kind = fields[0].upper()
        # Composite expressions may contain DOMAIN-SUFFIX text but are not
        # unconditional domain rules. Keep them visible as conditional context.
        if kind in {"AND", "OR", "NOT"}:
            if "DOMAIN" in line.upper():
                conditional_domain_lines.append((line_no, line))
            continue
        if kind not in {"DOMAIN", "DOMAIN-SUFFIX"}:
            continue
        if len(fields) < 3:
            ignored_domain_lines.append((line_no, line))
            continue
        domain = fields[1].lower().lstrip(".")
        policy = fields[2].upper()  # Policy is field 3; later fields are options.
        if not DOMAIN_RE.fullmatch(domain) or policy not in POLICIES:
            ignored_domain_lines.append((line_no, line))
            continue
        # Absolute config line number, not a line number relative to [Rule].
        absolute_line = content[:start].count("\n") + line_no
        rules.append(DomainRule(kind, domain, policy, absolute_line, line))
    rules.sort(key=lambda item: item.line)
    return rules, conditional_domain_lines, ignored_domain_lines


def matches_host(host: str, rules: list[DomainRule]):
    host = host.lower().rstrip(".")
    hits = []
    for rule in rules:
        if rule.kind == "DOMAIN":
            matched = host == rule.domain
        else:
            matched = host == rule.domain or host.endswith("." + rule.domain)
        if matched:
            hits.append(rule)
    return hits


def analyze_candidate(domain: str, is_suffix: bool, rules: list[DomainRule]):
    """Return apex winner and (for source suffixes) observed scope winners.

    The suffix scope is sampled at every existing exact/suffix boundary under
    that suffix. Rule order is evaluated independently for each representative
    host, so disjoint subdomains are not mislabeled as same-host conflicts.
    """
    apex_hits = matches_host(domain, rules)
    apex_winner = apex_hits[0] if apex_hits else None
    scope = {}
    if is_suffix:
        probes = {domain}
        for rule in rules:
            if rule.domain == domain or rule.domain.endswith("." + domain):
                probes.add(rule.domain)
                if rule.kind == "DOMAIN-SUFFIX":
                    probes.add("probe." + rule.domain)
        for host in sorted(probes):
            hits = matches_host(host, rules)
            if hits:
                scope[host] = hits[0]
    else:
        if apex_winner:
            scope[domain] = apex_winner
    policies = {winner.policy for winner in scope.values()}
    return {
        "apex_hits": apex_hits,
        "apex_winner": apex_winner,
        "scope_winners": scope,
        "scope_policies": policies,
    }
