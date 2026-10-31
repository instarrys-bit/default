#!/usr/bin/env python3
"""Shared ordered parser and indexed matcher for canonical Shadowrocket domain rules."""
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


def ancestors(domain: str):
    labels = domain.split(".")
    for i in range(len(labels)):
        yield ".".join(labels[i:])


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
    base_line = content[:start].count("\n")
    for line_no, raw in enumerate(block.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = [part.strip() for part in line.split(",")]
        kind = fields[0].upper()
        if kind in {"AND", "OR", "NOT"}:
            if "DOMAIN" in line.upper():
                conditional_domain_lines.append((base_line + line_no, line))
            continue
        if kind not in {"DOMAIN", "DOMAIN-SUFFIX"}:
            continue
        if len(fields) < 3:
            ignored_domain_lines.append((base_line + line_no, line))
            continue
        domain = fields[1].lower().lstrip(".")
        policy = fields[2].upper()
        if not DOMAIN_RE.fullmatch(domain) or policy not in POLICIES:
            ignored_domain_lines.append((base_line + line_no, line))
            continue
        rules.append(DomainRule(kind, domain, policy, base_line + line_no, line))
    rules.sort(key=lambda item: item.line)
    return rules, conditional_domain_lines, ignored_domain_lines


class RuleIndex:
    def __init__(self, rules: list[DomainRule]):
        self.rules = rules
        self.exact = {}
        self.suffix = {}
        self.under = {}
        for rule in rules:
            target = self.exact if rule.kind == "DOMAIN" else self.suffix
            target.setdefault(rule.domain, []).append(rule)
            for parent in ancestors(rule.domain):
                self.under.setdefault(parent, []).append(rule)

    def matches_host(self, host: str):
        host = host.lower().rstrip(".")
        hits = list(self.exact.get(host, []))
        for parent in ancestors(host):
            hits.extend(self.suffix.get(parent, []))
        hits.sort(key=lambda item: item.line)
        return hits


def matches_host(host: str, rules):
    index = rules if isinstance(rules, RuleIndex) else RuleIndex(rules)
    return index.matches_host(host)


def analyze_candidate(domain: str, is_suffix: bool, rules):
    """Resolve first-match policy for apex and representative hosts in a source suffix."""
    index = rules if isinstance(rules, RuleIndex) else RuleIndex(rules)
    apex_hits = index.matches_host(domain)
    apex_winner = apex_hits[0] if apex_hits else None
    scope = {}
    if is_suffix:
        probes = {domain}
        for rule in index.under.get(domain, []):
            probes.add(rule.domain)
            if rule.kind == "DOMAIN-SUFFIX":
                probes.add("probe." + rule.domain)
        for host in sorted(probes):
            hits = index.matches_host(host)
            if hits:
                scope[host] = hits[0]
    elif apex_winner:
        scope[domain] = apex_winner
    policies = {winner.policy for winner in scope.values()}
    return {
        "apex_hits": apex_hits,
        "apex_winner": apex_winner,
        "scope_winners": scope,
        "scope_policies": policies,
    }
