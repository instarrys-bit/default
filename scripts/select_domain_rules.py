#!/usr/bin/env python3
"""Approval-gated selector; canonical uu.conf is authoritative and read-only."""
from __future__ import annotations

if __import__("os").environ.get("AUTOMATION_WRITE_GUARD") == "1":
    from fenced_file_writer import install_write_guard as _install_write_guard
    _install_write_guard()


import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from domain_rule_engine import load_domain_rules
from audit_ruleset_config_overlap import scope_covers_candidate

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "uu.conf"
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
    assert scope_covers_candidate("exact_candidate", "api.example.com", "DOMAIN-SUFFIX", "example.com")
    assert scope_covers_candidate("suffix_candidate", "example.com", "DOMAIN-SUFFIX", "example.com")
    assert not scope_covers_candidate("suffix_candidate", "example.com", "DOMAIN", "api.example.com")
    assert not scope_covers_candidate("suffix_candidate", "example.com", "DOMAIN-SUFFIX", "api.example.com")
    print("PASS: full-scope coverage only; no precedence or REJECT config analysis")


def main() -> None:
    import sys
    if "--self-test" in sys.argv:
        self_test()
        return
    candidates = load_candidates()
    rules, conditional, ignored = load_domain_rules(CONFIG)
    # REJECT decisions in uu.conf are user-owned and excluded from this tool.
    rules = [rule for rule in rules if rule.policy in {"DIRECT", "PROXY"}]
    conditional = [item for item in conditional if item[1].rsplit(",", 1)[-1].strip().upper() != "REJECT"]
    approvals = load_approvals(candidates)
    stats = defaultdict(int)
    review, pending, generated = [], [], []

    for domain, is_suffix in candidates.items():
        scope = "suffix_candidate" if is_suffix else "exact_candidate"
        matches = [
            rule for rule in rules
            if scope_covers_candidate(scope, domain, rule.kind, rule.domain)
        ]
        approval = approvals.get(domain)
        if matches:
            policies = {rule.policy for rule in matches}
            evidence = "; ".join(
                f"{rule.kind},{rule.domain} => {rule.policy} (line {rule.line})"
                for rule in matches
            )
            if len(policies) > 1:
                stats["mixed_scope_policy_coverage"] += 1
                review.append((domain, "multiple fully covering config scopes carry different policies; no winner selected", evidence))
            else:
                config_policy = next(iter(policies))
                stats["fully_covered_by_config_scope"] += 1
                if approval and approval["policy"] != config_policy:
                    stats["approval_disagrees_with_config_scope"] += 1
                    review.append((domain, f"approval {approval['policy']} differs from fully covering config scope {config_policy}", evidence))
            continue

        if approval is None:
            stats["unreviewed_without_full_scope_coverage"] += 1
            pending.append(domain)
            continue
        kind = "DOMAIN-SUFFIX" if is_suffix else "DOMAIN"
        generated.append(f"{kind},{domain},{approval['policy']}")
        stats["approved_new_rules"] += 1

    generated.sort()
    review.sort()
    pending.sort()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(generated) + ("\n" if generated else ""), encoding="utf-8")
    report = [
        "# Domain rule selector scope audit", "",
        f"- Audit time: {datetime.now(timezone.utc).isoformat()}",
        f"- Pinned source SHA-1: `{EXPECTED_GIT_BLOB_SHA1}`",
        f"- Candidate count: {len(candidates)}",
        f"- Explicit DIRECT/PROXY DOMAIN / DOMAIN-SUFFIX config rules parsed: {len(rules)}",
        f"- Non-REJECT conditional composite rules containing DOMAIN terms (not flattened): {len(conditional)}",
        f"- Malformed or unsupported simple domain rules held aside: {len(ignored)}",
        f"- Explicit approvals: {len(approvals)}", "",
        "## Results", "", "| Classification | Count |", "|---|---:|",
    ]
    for key in ("fully_covered_by_config_scope", "mixed_scope_policy_coverage",
                "approval_disagrees_with_config_scope", "unreviewed_without_full_scope_coverage",
                "approved_new_rules"):
        report.append(f"| {key} | {stats[key]} |")
    report += ["", "## Review queue", "", "| Candidate | Reason | Config scope evidence |", "|---|---|---|"]
    report += [f"| `{domain}` | {reason} | {evidence} |" for domain, reason, evidence in review]
    report += [
        "", "## Pending candidates", "",
        f"Unreviewed candidates without a fully covering DIRECT/PROXY config scope: {len(pending)}. No policy is inferred and none are emitted.",
        "", "## Output contract", "",
        "- Only DOMAIN or DOMAIN-SUFFIX entries with an explicitly approved DIRECT/PROXY/REJECT policy are generated.",
        "- A candidate is covered only by a single explicit DIRECT/PROXY config scope that fully contains its complete source scope.",
        "- Child exact or child-suffix exceptions do not suppress broader suffix candidates.",
        "- REJECT rules in uu.conf are excluded from automated analysis; blocking decisions remain user-owned.",
        "- Mixed-policy coverage is held for review without selecting a winner.",
        "- No rule order, first-match policy, or precedence is inferred.",
        "- Conditional AND/OR/NOT rules are counted but are not flattened into unconditional domain rules.",
        "- Existing uu.conf, DNS, nodes, rule order, and subscription are never modified.",
        f"- Generated rules file: `{OUTPUT.relative_to(ROOT)}` ({len(generated)} rules)", "",
    ]
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
