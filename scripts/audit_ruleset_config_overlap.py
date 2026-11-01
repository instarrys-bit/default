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


def match_candidate(domain: str, policy: str, rules: list[tuple[int, str]]) -> dict:
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


def audit(config_text: str, ledger: dict) -> dict:
    boundary = first_ruleset_line(config_text)
    rules = prior_rule_lines(config_text)
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
        match = match_candidate(domain, policy, rules)
        result = {
            "domain": domain, "policy": policy,
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
        "candidate_count": len(results),
        "status_counts": dict(sorted(counts.items())),
        "results": sorted(results, key=lambda x: x["domain"]),
        "errors": errors,
        "passed": not errors,
        "limitations": [
            "Only rules before the first RULE-SET reference are considered as higher-priority rules.",
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
