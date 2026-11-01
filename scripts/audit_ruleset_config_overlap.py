#!/usr/bin/env python3
"""Read-only audit of candidate domains against rules preceding the first RULE-SET."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
LEDGER = ROOT / "sources" / "domain_reviews.json"
REPORT_JSON = ROOT / "reports" / "ruleset-config-overlap-audit.json"
REPORT_MD = ROOT / "reports" / "ruleset-config-overlap-audit.md"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$", re.I)
DOMAIN_ATOM_RE = re.compile(r"(DOMAIN-SUFFIX|DOMAIN),([A-Za-z0-9.-]+)", re.I)
POLICIES = {"DIRECT", "PROXY", "REJECT"}
from domain_rule_engine import DomainRule, RuleIndex, analyze_candidate


def domain_matches(domain: str, kind: str, target: str) -> bool:
    target = target.lower().strip(".")
    domain = domain.lower().strip(".")
    return domain == target or (kind.upper() == "DOMAIN-SUFFIX" and domain.endswith("." + target))


def first_ruleset_line(config_text: str) -> int | None:
    in_rules = False
    for number, raw in enumerate(config_text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_rules = line[1:-1].strip().lower() == "rule"
            continue
        if in_rules and line and not line.startswith("#") and line.upper().startswith("RULE-SET,"):
            return number
    return None


def prior_rule_lines(config_text: str) -> list[tuple[int, str]]:
    boundary = first_ruleset_line(config_text)
    in_rules = False
    result = []
    for number, raw in enumerate(config_text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_rules = line[1:-1].strip().lower() == "rule"
            continue
        if not in_rules:
            continue
        if boundary is not None and number >= boundary:
            break
        if line and not line.startswith("#"):
            result.append((number, line))
    return result


def scope_intersects(candidate_scope: str, domain: str, kind: str, target: str) -> bool:
    domain, target = domain.lower().strip("."), target.lower().strip(".")
    if candidate_scope == "exact_candidate":
        return domain_matches(domain, kind, target)
    if kind == "DOMAIN":
        return target == domain or target.endswith("." + domain)
    return (
        target == domain or target.endswith("." + domain)
        or domain.endswith("." + target)
    )


def match_candidate(domain: str, policy: str, rules: list[tuple[int, str]], scope: str = "exact_candidate") -> dict:
    if scope == "suffix_candidate":
        parsed = []
        for number, line in rules:
            fields = [part.strip() for part in line.split(",")]
            if len(fields) >= 3 and fields[0].upper() in {"DOMAIN", "DOMAIN-SUFFIX"}:
                parsed.append(DomainRule(fields[0].upper(), fields[1].lower(), fields[2].upper(), number, line))
        analysis = analyze_candidate(domain, True, RuleIndex(parsed))
        winners = analysis["scope_winners"]
        policies = analysis["scope_policies"]
        if any(value != policy for value in policies):
            first = next((winner for winner in winners.values() if winner.policy != policy), None)
            return {
                "status": "CONFLICT", "line": first.line if first else None,
                "rule": first.raw if first else None,
                "effective_policy": first.policy if first else None,
                "reason": "Prior first-match rules produce a conflicting policy within suffix scope"
            }
        if policies:
            apex = analysis["apex_winner"]
            fully_covered = bool(
                apex and apex.kind == "DOMAIN-SUFFIX"
                and (domain == apex.domain or domain.endswith("." + apex.domain))
                and all(winner.policy == policy for winner in winners.values())
            )
            first = next(iter(winners.values()))
            return {
                "status": "ALREADY_COVERED" if fully_covered else "POTENTIAL_MATCH",
                "line": first.line, "rule": first.raw, "effective_policy": policy,
                "reason": "Prior first-match rules intersect candidate suffix scope"
            }
    for number, line in rules:
        fields = [part.strip() for part in line.split(",")]
        kind = fields[0].upper()
        if kind in {"DOMAIN", "DOMAIN-SUFFIX"} and len(fields) >= 3:
            if domain_matches(domain, kind, fields[1]):
                matched_policy = fields[2].upper()
                return {
                    "status": "ALREADY_COVERED" if matched_policy == policy else "CONFLICT",
                    "line": number, "rule": line, "effective_policy": matched_policy,
                    "reason": "Prior first-match exact/suffix domain rule"
                }
        elif kind == "DOMAIN-KEYWORD" and len(fields) >= 3:
            if fields[1].lower() in domain:
                return {
                    "status": "POTENTIAL_MATCH", "line": number, "rule": line,
                    "effective_policy": fields[2].upper(),
                    "reason": "Prior DOMAIN-KEYWORD may match this candidate"
                }
        elif kind == "URL-REGEX":
            if len(fields) < 3:
                return {"status": "UNRESOLVED_RULE", "line": number, "rule": line,
                        "effective_policy": None, "reason": "Malformed prior URL-REGEX"}
            pattern = ",".join(fields[1:-1])
            try:
                compiled = re.compile(pattern, re.I)
            except re.error:
                return {"status": "UNRESOLVED_RULE", "line": number, "rule": line,
                        "effective_policy": fields[-1].upper(), "reason": "Prior URL-REGEX cannot be compiled"}
            if compiled.search("https://" + domain) or compiled.search("http://" + domain):
                return {"status": "POTENTIAL_MATCH", "line": number, "rule": line,
                        "effective_policy": fields[-1].upper(), "reason": "Prior URL-REGEX matches candidate URL"}
        elif kind in {"AND", "OR", "NOT"}:
            for atom_kind, target in DOMAIN_ATOM_RE.findall(line):
                if domain_matches(domain, atom_kind, target):
                    return {"status": "CONDITIONAL_POTENTIAL", "line": number, "rule": line,
                            "effective_policy": fields[-1].upper() if fields[-1].upper() in POLICIES else None,
                            "reason": "Prior compound rule contains a matching domain operand; other operands are not evaluated"}
        elif kind == "FINAL" and len(fields) >= 2 and fields[1].upper() in POLICIES:
            return {"status": "ALREADY_COVERED" if fields[1].upper() == policy else "CONFLICT",
                    "line": number, "rule": line, "effective_policy": fields[1].upper(),
                    "reason": "Prior FINAL rule matches all remaining traffic"}
    return {"status": "NOT_COVERED_BY_PRIOR_DOMAIN_RULES", "line": None, "rule": None,
            "effective_policy": None, "reason": "No earlier exact, suffix, keyword, URL-REGEX or conditional domain match found"}


def parse_skip_proxy(config_text: str) -> list[str]:
    if config_text.count("[General]") != 1 or config_text.count("[Rule]") != 1:
        raise ValueError("cannot isolate [General] section for skip-proxy audit")
    block = config_text.split("[General]", 1)[1].split("[Rule]", 1)[0]
    for raw in block.splitlines():
        line = raw.strip()
        if line.lower().startswith("skip-proxy") and "=" in line:
            return [item.strip().lower() for item in line.split("=", 1)[1].split(",") if item.strip()]
    return []


def skip_proxy_match(domain: str, entries: list[str]) -> str | None:
    for entry in entries:
        if "/" in entry or ":" in entry:
            continue
        if entry.startswith("*."):
            suffix = entry[2:]
            if domain == suffix or domain.endswith("." + suffix):
                return entry
        elif domain == entry:
            return entry
    return None


def audit(config_text: str, ledger: dict) -> dict:
    boundary = first_ruleset_line(config_text)
    rules = prior_rule_lines(config_text)
    skip_proxy_entries = parse_skip_proxy(config_text)
    results = []
    errors = []
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
        match = match_candidate(domain, policy, rules, scope)
        if match["status"] == "NOT_COVERED_BY_PRIOR_DOMAIN_RULES":
            bypass = skip_proxy_match(domain, skip_proxy_entries)
            if bypass:
                match = {"status": "ALREADY_COVERED" if policy == "DIRECT" else "CONFLICT",
                         "line": None, "rule": "skip-proxy = " + bypass,
                         "effective_policy": "DIRECT", "reason": "Existing General skip-proxy entry"}
        result = {
            "domain": domain, "policy": policy, "source_entry_type": scope,
            "ledger_status": str(item.get("status", "UNKNOWN")),
            **match
        }
        results.append(result)
        if result["ledger_status"] == "APPROVED" and result["status"] != "NOT_COVERED_BY_PRIOR_DOMAIN_RULES":
            errors.append("APPROVED candidate overlaps prior config rule: " + domain + " (" + result["status"] + ")")
    counts = {}
    for result in results:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {
        "schema_version": 1,
        "config_path": "shadowrocket/ss.conf",
        "config_is_read_only": True,
        "first_ruleset_line": boundary,
        "prior_rule_line_count": len(rules),
        "skip_proxy_entry_count": len(skip_proxy_entries),
        "candidate_count": len(results),
        "status_counts": dict(sorted(counts.items())),
        "results": sorted(results, key=lambda x: x["domain"]),
        "errors": errors,
        "passed": not errors,
        "limitations": [
            "Only rules before the first RULE-SET reference are considered as higher-priority rules. DOMAIN-SUFFIX candidates are checked against the full suffix scope, including exact descendant rules.",
            "AND/OR/NOT operands are flagged as potential matches; compound truth is not inferred.",
            "DOMAIN-KEYWORD and URL-REGEX matches are reported as potential, not guaranteed, coverage.",
            "IP-based and runtime DNS-dependent matches cannot be established from domain names alone.",
            "The audit never edits ss.conf, DNS, MITM, or RULE-SET references."
        ]
    }


def main() -> int:
    report = audit(CONFIG.read_text(encoding="utf-8-sig"), json.loads(LEDGER.read_text(encoding="utf-8")))
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# RULE-SET / user-config overlap audit", "",
        "- Authority: read-only shadowrocket/ss.conf",
        f"- First RULE-SET line: {report['first_ruleset_line']}",
        f"- Earlier active rules: {report['prior_rule_line_count']}",
        f"- Ledger candidates: {report['candidate_count']}",
        f"- Result: {'PASS' if report['passed'] else 'FAIL'}", "",
        "## Status counts", ""
    ]
    lines.extend(f"- {name}: {count}" for name, count in report["status_counts"].items())
    lines.extend(["", "## Findings", ""])
    lines.extend(
        f"- {x['domain']} ({x['policy']}): {x['status']} — line {x['line']}: {x['reason']}"
        for x in report["results"] if x["status"] != "NOT_COVERED_BY_PRIOR_DOMAIN_RULES"
    )
    if not any(x["status"] != "NOT_COVERED_BY_PRIOR_DOMAIN_RULES" for x in report["results"]):
        lines.append("- No prior domain-rule overlaps found.")
    lines.extend(["", "## Errors", ""])
    lines.extend("- " + error for error in report["errors"]) if report["errors"] else lines.append("- None")
    lines.extend(["", "Read-only report. No configuration or rule-set references were changed.", ""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "candidate_count": report["candidate_count"],
                      "status_counts": report["status_counts"], "errors": report["errors"]},
                     ensure_ascii=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
