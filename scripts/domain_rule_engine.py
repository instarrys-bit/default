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
        raise ValueError("user-managed shadowrocket/ss.conf baseline is missing")
    content = config_path.read_text(encoding="utf-8")
    if content.count("[Rule]") != 1 or content.count("[Host]") != 1:
        raise ValueError("cannot uniquely isolate user-config [Rule] section")
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



def inspect_suffix_scope(domain: str, policy: str, rules, conditional, protected, skip_proxy=()):
    """Check full-scope coverage and safety holds without evaluating rule order."""
    domain = domain.lower().rstrip(".")
    policy = policy.upper()

    # Only a parent/equal DOMAIN-SUFFIX rule covers the complete suffix scope.
    # Exact or child-suffix rules are narrower exceptions and do not suppress it.
    covering = [
        rule for rule in rules.rules
        if rule.policy != "REJECT"
        and rule.kind == "DOMAIN-SUFFIX"
        and (domain == rule.domain or domain.endswith("." + rule.domain))
    ]
    if covering:
        policies = {rule.policy for rule in covering}
        if len(policies) > 1:
            return "REVIEW", "Multiple fully covering config suffix scopes declare different policies; no winner is selected"
        covered_policy = next(iter(policies))
        if covered_policy != policy:
            return "CONFLICT", "A fully covering config suffix scope declares a different policy; rule order is not evaluated"

    # Conditional rules remain a conservative review hold, not a precedence test.
    for _, raw in conditional:
        if raw.rsplit(",", 1)[-1].strip().upper() == "REJECT":
            continue
        for kind, match in re.findall(r"(DOMAIN-SUFFIX|DOMAIN),([A-Za-z0-9.-]+)", raw, re.I):
            match = match.lower().strip(".")
            if kind.upper() == "DOMAIN":
                intersects = match == domain or match.endswith("." + domain)
            else:
                intersects = (
                    match == domain
                    or match.endswith("." + domain)
                    or domain.endswith("." + match)
                )
            if intersects:
                return "REVIEW", "Suffix scope intersects an existing conditional domain rule"

    for host in protected.get("protected_exact", []):
        host = host.lower().strip(".")
        if host == domain or host.endswith("." + domain):
            return "RISK_HOLD", "Suffix scope would include protected exact host " + host

    for suffix in protected.get("protected_suffixes", []):
        suffix = suffix.lower().strip(".")
        if (
            suffix == domain
            or suffix.endswith("." + domain)
            or domain.endswith("." + suffix)
        ):
            return "RISK_HOLD", "Suffix scope intersects protected suffix " + suffix

    # A single exact skip-proxy host is only a narrower exception. A wildcard
    # parent is the only skip-proxy entry that can cover the whole suffix.
    if policy != "DIRECT":
        for entry in skip_proxy:
            entry = entry.lower().strip()
            if "/" in entry or ":" in entry or not entry.startswith("*."):
                continue
            suffix = entry[2:].strip(".")
            if domain == suffix or domain.endswith("." + suffix):
                return "CONFLICT", "Suffix scope is fully covered by direct-bypass skip-proxy entry " + entry

    return None, None
