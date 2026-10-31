#!/usr/bin/env python3
"""Approval-gated selector; canonical ss.conf is authoritative and read-only."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from domain_rule_engine import RuleIndex, analyze_candidate, load_domain_rules

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
APPROVALS = ROOT / "sources" / "policy_approvals.json"
REPORT = ROOT / "reports" / "rule-selector-audit.md"
OUTPUT = ROOT / "reports" / "approved-domain-rules.list"
SOURCE_URL = "https://raw.githubusercontent.com/ithtelab/sr-adblock/release/ruleset/ad-domain-lite.list"
EXPECTED_GIT_BLOB_SHA1 = "ec23c2d1280ea4a59717816716b8ccb569dac624"
EXPECTED_ENTRIES = 56516
MAX_BYTES = 2_000_000
POLICIES = {"DIRECT", "PROXY", "REJECT"}
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load_candidates() -> dict[str, bool]:
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Shadowrocket-rule-selector/2.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        final = urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            fail(f"unexpected source response: {response.geturl()}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        fail("external source exceeds 2 MB")
    actual = git_blob_sha1(data)
    if actual != EXPECTED_GIT_BLOB_SHA1:
        fail(f"source drift: expected {EXPECTED_GIT_BLOB_SHA1}, received {actual}; manual review required")
    candidates = {}
    for number, raw in enumerate(data.decode("utf-8").splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if value != raw or any(ch.isspace() for ch in value):
            fail(f"invalid whitespace at source line {number}")
        is_suffix = value.startswith(".")
        domain = value[1:] if is_suffix else value
        if not DOMAIN_RE.fullmatch(domain):
            fail(f"invalid domain at source line {number}: {raw!r}")
        key = domain.lower()
        if key in candidates:
            fail(f"duplicate candidate at source line {number}: {key}")
        candidates[key] = is_suffix
    if len(candidates) != EXPECTED_ENTRIES:
        fail(f"candidate count mismatch: expected {EXPECTED_ENTRIES}, got {len(candidates)}")
    return candidates


def load_approvals(candidates: dict[str, bool]) -> dict[str, dict[str, str]]:
    if not APPROVALS.is_file():
        fail("sources/policy_approvals.json is missing")
    try:
        payload = json.loads(APPROVALS.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"approval manifest is invalid: {exc}")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("approvals"), list):
        fail("approval manifest schema is invalid")
    approvals = {}
    for item in payload["approvals"]:
        if not isinstance(item, dict):
            fail("each approval must be an object")
        domain = str(item.get("domain", "")).lower().strip()
        policy = str(item.get("policy", "")).upper().strip()
        evidence = str(item.get("evidence", "")).strip()
        if not DOMAIN_RE.fullmatch(domain):
            fail(f"invalid approved domain: {domain!r}")
        if domain not in candidates:
            fail(f"approved domain is not in pinned candidate source: {domain}")
        if policy not in POLICIES:
            fail(f"unsupported policy for {domain}: {policy}")
        if not evidence:
            fail(f"approval requires evidence note: {domain}")
        if domain in approvals:
            fail(f"duplicate approval: {domain}")
        approvals[domain] = {"policy": policy, "evidence": evidence}
    return approvals


def self_test() -> None:
    from domain_rule_engine import DomainRule, matches_host, analyze_candidate
    sample = [
        DomainRule("DOMAIN-SUFFIX", "shop.example.com", "DIRECT", 5, ""),
        DomainRule("DOMAIN-SUFFIX", "example.com", "PROXY", 10, ""),
        DomainRule("DOMAIN", "ads.example.com", "REJECT", 20, ""),
        DomainRule("DOMAIN", "exact.test", "REJECT", 40, ""),
        DomainRule("DOMAIN", "exact.test", "DIRECT", 50, ""),
    ]
    assert matches_host("api.example.com", sample)[0].policy == "PROXY"
    assert matches_host("ads.example.com", sample)[0].policy == "PROXY"
    assert matches_host("exact.test", sample)[0].policy == "REJECT"
    varied = analyze_candidate("example.com", True, sample)
    assert varied["scope_policies"] == {"PROXY", "DIRECT"}
    exact = analyze_candidate("exact.test", False, sample)
    assert exact["apex_winner"].policy == "REJECT"
    assert len(exact["apex_hits"]) == 2
    print("PASS: ordered first-match, suffix scope, and shadowing tests")


def main() -> None:
    import sys
    if "--self-test" in sys.argv:
        self_test()
        return
    candidates = load_candidates()
    rules, conditional, ignored = load_domain_rules(CONFIG)
    rule_index = RuleIndex(rules)
    approvals = load_approvals(candidates)
    stats = defaultdict(int)
    review, pending, generated = [], [], []

    for domain, is_suffix in candidates.items():
        result = analyze_candidate(domain, is_suffix, rule_index)
        policies = result["scope_policies"]
        approval = approvals.get(domain)
        if len(policies) > 1:
            stats["suffix_scope_policy_variation"] += 1
            winners = sorted({(r.policy, r.line, r.domain) for r in result["scope_winners"].values()})
            evidence = "; ".join(f"{p} line {line} ({rule_domain})" for p, line, rule_domain in winners)
            review.append((domain, "source suffix spans different effective policies", evidence))
            continue
        winner = result["apex_winner"]
        if winner:
            stats["already_governed_by_original_config"] += 1
            if approval and approval["policy"] != winner.policy:
                stats["approval_disagrees_with_original_config"] += 1
                review.append((domain, f"approval {approval['policy']} disagrees with original first-match {winner.policy}",
                               f"line {winner.line}: {winner.kind} {winner.domain}"))
            continue
        if approval is None:
            stats["unreviewed_no_existing_domain_rule"] += 1
            pending.append(domain)
            continue
        generated.append(f"DOMAIN,{domain},{approval['policy']}")
        stats["approved_new_exact_rules"] += 1

    generated.sort()
    review.sort()
    pending.sort()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(generated) + ("\n" if generated else ""), encoding="utf-8")
    report = [
        "# Domain rule selector audit", "",
        f"- Audit time: {datetime.now(timezone.utc).isoformat()}",
        f"- Pinned source SHA-1: `{EXPECTED_GIT_BLOB_SHA1}`",
        f"- Candidate count: {len(candidates)}",
        f"- Ordered unconditional DOMAIN / DOMAIN-SUFFIX rules parsed: {len(rules)}",
        f"- Conditional composite rules containing DOMAIN terms (not flattened): {len(conditional)}",
        f"- Malformed or unsupported simple domain rules held aside: {len(ignored)}",
        f"- Explicit approvals: {len(approvals)}", "",
        "## Results", "", "| Classification | Count |", "|---|---:|",
    ]
    for key in ("already_governed_by_original_config", "suffix_scope_policy_variation",
                "approval_disagrees_with_original_config", "unreviewed_no_existing_domain_rule",
                "approved_new_exact_rules"):
        report.append(f"| {key} | {stats[key]} |")
    report += ["", "## Review queue", "", "| Candidate | Reason | Original config evidence |", "|---|---|---|"]
    report += [f"| `{domain}` | {reason} | {evidence} |" for domain, reason, evidence in review]
    report += [
        "", "## Pending candidates", "",
        f"Unreviewed candidates without an existing unconditional domain-rule match: {len(pending)}. No policy is inferred and none are emitted.",
        "", "## Output contract", "",
        "- Only `DOMAIN,<domain>,DIRECT|PROXY|REJECT` is generated.",
        "- The first matching unconditional DOMAIN or DOMAIN-SUFFIX rule in canonical ss.conf determines the existing effective domain policy.",
        "- Later matching rules are shadowed by original rule order; they do not override the winner.",
        "- Source suffix scopes with different effective policies are quarantined for review.",
        "- Conditional AND/OR/NOT rules are kept separate and are not treated as unconditional domain rules.",
        "- No upstream policy is adopted; every new rule requires an explicit approval and evidence note.",
        "- Existing ss.conf, DNS, nodes, rule order, and subscription are never modified.",
        f"- Generated rules file: `{OUTPUT.relative_to(ROOT)}` ({len(generated)} rules)", "",
    ]
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
