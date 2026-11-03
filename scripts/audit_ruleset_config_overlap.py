#!/usr/bin/env python3
"""Read-only scope-coverage audit between candidate domains and user-owned config."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
LEDGER = ROOT / "sources" / "domain_reviews.json"
REPORT_JSON = ROOT / "reports" / "ruleset-config-overlap-audit.json"
REPORT_MD = ROOT / "reports" / "ruleset-config-overlap-audit.md"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$", re.I)
POLICIES = {"DIRECT", "PROXY", "REJECT"}
from domain_rule_engine import DomainRule, RuleIndex, ancestors
from json_document_store import read_document


def all_rule_lines(config_text: str) -> list[tuple[int, str]]:
    """Return all active [Rule] entries without assigning precedence."""
    in_rules = False
    result = []
    for number, raw in enumerate(config_text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_rules = line[1:-1].strip().lower() == "rule"
            continue
        if in_rules and line and not line.startswith("#"):
            result.append((number, line))
    return result


def scope_covers_candidate(candidate_scope: str, domain: str, rule_kind: str, target: str) -> bool:
    """Whether one explicit config scope fully contains the candidate scope."""
    domain = domain.lower().strip(".")
    target = target.lower().strip(".")
    rule_kind = rule_kind.upper()
    if candidate_scope == "exact_candidate":
        return target == domain or (
            rule_kind == "DOMAIN-SUFFIX" and domain.endswith("." + target)
        )
    if candidate_scope == "suffix_candidate":
        return rule_kind == "DOMAIN-SUFFIX" and (
            domain == target or domain.endswith("." + target)
        )
    raise ValueError("unsupported candidate scope: " + candidate_scope)


def scope_intersects(candidate_scope: str, domain: str, kind: str, target: str) -> bool:
    """Broad overlap test used only for cross-policy ruleset restoration checks."""
    domain, target = domain.lower().strip("."), target.lower().strip(".")
    if candidate_scope == "exact_candidate":
        return domain == target or (kind.upper() == "DOMAIN-SUFFIX" and domain.endswith("." + target))
    if kind.upper() == "DOMAIN":
        return target == domain or target.endswith("." + domain)
    return target == domain or target.endswith("." + domain) or domain.endswith("." + target)


def parse_skip_proxy(config_text: str) -> list[str]:
    if config_text.count("[General]") != 1 or config_text.count("[Rule]") != 1:
        raise ValueError("cannot isolate [General] section for skip-proxy audit")
    block = config_text.split("[General]", 1)[1].split("[Rule]", 1)[0]
    for raw in block.splitlines():
        line = raw.strip()
        if line.lower().startswith("skip-proxy") and "=" in line:
            return [item.strip().lower() for item in line.split("=", 1)[1].split(",") if item.strip()]
    return []


def skip_proxy_match(domain: str, entries: list[str], scope: str = "exact_candidate") -> str | None:
    """Return only skip-proxy entries that cover the complete candidate scope."""
    domain = domain.lower().strip(".")
    for entry in entries:
        if "/" in entry or ":" in entry:
            continue
        if entry.startswith("*."):
            suffix = entry[2:].strip(".")
            if domain == suffix or domain.endswith("." + suffix):
                return entry
        elif scope == "exact_candidate" and domain == entry:
            return entry
    return None


def prepare_rules(rules: list[tuple[int, str]]) -> RuleIndex:
    """Build an unordered scope index for explicit config domain rules."""
    parsed = []
    for number, line in rules:
        fields = [part.strip() for part in line.split(",")]
        if len(fields) < 3 or fields[0].upper() not in {"DOMAIN", "DOMAIN-SUFFIX"}:
            continue
        domain = fields[1].lower().strip(".")
        policy = fields[2].upper()
        if policy in {"DIRECT", "PROXY", "REJECT"}:
            parsed.append(DomainRule(fields[0].upper(), domain, policy, number, line))
    return RuleIndex(parsed)


def find_covering_rules(domain: str, scope: str, prepared_rules: RuleIndex):
    domain = domain.lower().rstrip(".")
    if scope == "exact_candidate":
        return prepared_rules.matches_host(domain)
    if scope == "suffix_candidate":
        matches = []
        for parent in ancestors(domain):
            matches.extend(prepared_rules.suffix.get(parent, []))
        return matches
    raise ValueError("unsupported candidate scope: " + scope)


def match_candidate(
    domain: str,
    policy: str,
    rules: list[tuple[int, str]],
    scope: str = "exact_candidate",
    prepared_rules: RuleIndex | None = None,
) -> dict:
    domain = domain.lower().rstrip(".")
    policy = policy.upper()
    index = prepared_rules if prepared_rules is not None else prepare_rules(rules)
    matches = [
        {"line": rule.line, "rule": rule.raw, "policy": rule.policy}
        for rule in find_covering_rules(domain, scope, index)
    ]
    matches.sort(key=lambda item: (item["rule"], item["policy"], item["line"]))

    if matches:
        policies = {item["policy"] for item in matches}
        if len(policies) > 1:
            status = "MIXED_POLICY_COVERAGE"
        elif next(iter(policies)) == policy:
            status = "ALREADY_COVERED"
        else:
            status = "CONFLICT"
        return {
            "status": status,
            "line": None,
            "rule": None,
            "effective_policy": None,
            "matches": matches,
            "reason": "One or more explicit config domain scopes fully cover this candidate; rule order is not evaluated",
        }

    return {
        "status": "NOT_COVERED_BY_CONFIG_SCOPE",
        "line": None,
        "rule": None,
        "effective_policy": None,
        "matches": [],
        "reason": "No single explicit DOMAIN or DOMAIN-SUFFIX config rule fully covers this candidate scope",
    }


def audit(config_text: str, ledger: dict) -> dict:
    rules = all_rule_lines(config_text)
    skip_proxy_entries = parse_skip_proxy(config_text)
    prepared_rules = prepare_rules(rules)
    results = []
    errors = []
    warnings = []

    for item in ledger.get("reviews", []):
        domain = str(item.get("domain", "")).lower().rstrip(".")
        policy = str(item.get("policy", item.get("classification", ""))).upper()
        if not DOMAIN_RE.fullmatch(domain):
            errors.append("Invalid ledger domain: " + domain)
            continue
        if policy not in POLICIES:
            continue
        scope = str(item.get("source_entry_type", "exact_candidate"))
        if scope not in {"exact_candidate", "suffix_candidate"}:
            errors.append("Unsupported ledger scope for " + domain + ": " + scope)
            continue

        match = match_candidate(domain, policy, rules, scope, prepared_rules)
        if match["status"] == "NOT_COVERED_BY_CONFIG_SCOPE":
            bypass = skip_proxy_match(domain, skip_proxy_entries, scope)
            if bypass:
                match = {
                    "status": "ALREADY_COVERED" if policy == "DIRECT" else "CONFLICT",
                    "line": None,
                    "rule": "skip-proxy = " + bypass,
                    "effective_policy": "DIRECT",
                    "matches": [{"line": None, "rule": "skip-proxy = " + bypass, "policy": "DIRECT"}],
                    "reason": "Existing skip-proxy entry fully covers the candidate scope; rule order is not evaluated",
                }

        result = {
            "domain": domain,
            "policy": policy,
            "source_entry_type": scope,
            "ledger_status": str(item.get("status", "UNKNOWN")),
            **match,
        }
        results.append(result)
        if result["ledger_status"] == "APPROVED" and result["status"] != "NOT_COVERED_BY_CONFIG_SCOPE":
            warnings.append(
                "APPROVED candidate is already covered by user-config scope; no rule precedence was inferred: "
                + domain + " (" + result["status"] + ")"
            )

    counts = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {
        "schema_version": 2,
        "config_path": "shadowrocket/ss.conf",
        "config_is_read_only": True,
        "config_rule_line_count": sum(1 for _, line in rules if len(line.split(",")) >= 3 and line.split(",", 1)[0].strip().upper() in {"DOMAIN", "DOMAIN-SUFFIX"} and line.split(",")[2].strip().upper() in {"DIRECT", "PROXY", "REJECT"}),
        "skip_proxy_entry_count": len(skip_proxy_entries),
        "candidate_count": len(results),
        "status_counts": dict(sorted(counts.items())),
        "results": sorted(results, key=lambda x: x["domain"]),
        "warnings": warnings,
        "errors": errors,
        "passed": not errors,
        "limitations": [
            "Explicit DOMAIN and DOMAIN-SUFFIX scopes with DIRECT, PROXY, and REJECT policies are compared.",
            "Explicit DOMAIN and DOMAIN-SUFFIX rules with DIRECT, PROXY, and REJECT policies are compared for full-scope coverage; rule precedence is not evaluated.",
            "A narrower exact or child-suffix exception does not suppress a broader suffix candidate.",
            "No rule order, first-match winner, or precedence is evaluated.",
            "DOMAIN-KEYWORD, URL-REGEX, compound rules, IP rules, and runtime DNS-dependent matches are not evaluated.",
            "The audit never edits ss.conf, DNS, MITM, or RULE-SET references.",
        ],
    }


def main() -> int:
    report = audit(CONFIG.read_text(encoding="utf-8-sig"), read_document(LEDGER, "reviews", {"reviews": []}))
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# RULE-SET / user-config scope coverage audit", "",
        "- Authority: read-only shadowrocket/ss.conf",
        f"- Explicit config rule lines: {report['config_rule_line_count']}",
        f"- Ledger candidates: {report['candidate_count']}",
        f"- Result: {'PASS' if report['passed'] else 'FAIL'}", "",
        "## Status counts", "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in report["status_counts"].items())
    lines.extend(["", "## Findings", ""])
    for item in report["results"]:
        if item["status"] == "NOT_COVERED_BY_CONFIG_SCOPE":
            continue
        matches = "; ".join(
            f"L{match['line']}: {match['rule']} [{match['policy']}]"
            for match in item.get("matches", [])
        )
        if item.get("rule") and not matches:
            matches = item["rule"]
        lines.append(
            f"- {item['domain']} ({item['policy']}): {item['status']} — {item['reason']}; "
            f"covering scopes: {matches or 'not listed'}"
        )
    if not any(x["status"] != "NOT_COVERED_BY_CONFIG_SCOPE" for x in report["results"]):
        lines.append("- No full-scope coverage found.")
    lines.extend(["", "## Errors", ""])
    lines.extend("- " + error for error in report["errors"]) if report["errors"] else lines.append("- None")
    lines.extend(["", "## Warnings", ""])
    lines.extend("- " + warning for warning in report["warnings"]) if report["warnings"] else lines.append("- None")
    lines.extend(["", "## Limitations", ""])
    lines.extend("- " + limitation for limitation in report["limitations"])
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["status_counts"], sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
